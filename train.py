import tensorflow as tf
import configuration
import img2txt
import time

FLAGS = tf.app.flags.FLAGS

tf.flags.DEFINE_string(flag_name="input_file_pattern",default_value="./data/ms_data/train-?????-of-00256",
                       docstring="File pattern/path of sharded TFRecord input files. example /ms_data/train-?????-of-00256")

tf.flags.DEFINE_string(flag_name="inception_checkpoint_file", default_value= "./data/inception_v3.ckpt",
                       docstring="Path to a pretrained inception_v3 model.")

tf.flags.DEFINE_string(flag_name="rnn_type", default_value= "lstm",
                       docstring="RNN cell type lstm/gru .")


tf.flags.DEFINE_string(flag_name="train_dir", default_value="./model/train",
                       docstring="Directory for saving and loading model checkpoints.")

tf.flags.DEFINE_boolean("train_inception", False,
                        "Whether to train inception submodel variables.")

tf.flags.DEFINE_integer("number_of_steps", 1, "Number of training steps.")
tf.flags.DEFINE_integer("log_every_n_steps", 1,
                        "Frequency at which loss and global step are logged.")

tf.logging.set_verbosity(tf.logging.INFO)


def main(unused_argv):
    assert FLAGS.input_file_pattern, "--input_file_pattern is required"
    assert FLAGS.train_dir, "--train_dir is required"

    model_config = configuration.ModelConfig()
    model_config.input_file_pattern = FLAGS.input_file_pattern
    model_config.inception_checkpoint_file = FLAGS.inception_checkpoint_file

    training_config = configuration.TrainingConfig()

    train_dir = FLAGS.train_dir
    if not tf.gfile.IsDirectory(train_dir):
        tf.logging.info("Creating training directory: %s", train_dir)
        tf.gfile.MakeDirs(train_dir)
    start_time = time.time()

    g = tf.Graph()
    with g.as_default():
        model = img2txt.Model(config=model_config,
                              mode="train",
                              rnn_type=FLAGS.rnn_type,
                              train_inception=FLAGS.train_inception)
        model.build()

        # Set up the learning rate.
        learning_rate_decay_fn = None
        if FLAGS.train_inception:
            learning_rate = tf.constant(training_config.train_inception_learning_rate)
        else:
            learning_rate = tf.constant(training_config.initial_learning_rate)
            if training_config.learning_rate_decay_factor > 0:
                num_batches_per_epoch = (training_config.num_examples_per_epoch /
                                         model_config.batch_size)
                decay_steps = int(num_batches_per_epoch *
                                  training_config.num_epochs_per_decay)

                def _learning_rate_decay_fn(learning_rate, global_step):
                    return tf.train.exponential_decay(
                        learning_rate,
                        global_step,
                        decay_steps=decay_steps,
                        decay_rate=training_config.learning_rate_decay_factor,
                        staircase=True)

                learning_rate_decay_fn = _learning_rate_decay_fn

            # Set up the training ops.
        train_op = tf.contrib.layers.optimize_loss(
            loss=model.total_loss,
            global_step=model.global_step,
            learning_rate=learning_rate,
            optimizer=training_config.optimizer,
            clip_gradients=training_config.clip_gradients,
            learning_rate_decay_fn=learning_rate_decay_fn)

        # Set up the Saver for saving and restoring model checkpoints.
        saver = tf.train.Saver(max_to_keep=training_config.max_checkpoints_to_keep)

        # Run training.
    tf.contrib.slim.learning.train(
        train_op,
        train_dir,
        log_every_n_steps=FLAGS.log_every_n_steps,
        graph=g,
        global_step=model.global_step,
        number_of_steps=FLAGS.number_of_steps,
        init_fn=model.init_fn,
        saver=saver)
    end_time = time.time()
    duration = end_time - start_time
    print(time.strftime('Start time :%Y-%m-%d %H:%M:%S', time.localtime(start_time)))
    print(time.strftime('End time :%Y-%m-%d %H:%M:%S', time.localtime(end_time)))
    m, s = divmod(duration, 60)
    h, m = divmod(m, 60)
    print("Total time %d:%02d:%02d" % (h, m, s))


if __name__ == "__main__":
    tf.app.run()
