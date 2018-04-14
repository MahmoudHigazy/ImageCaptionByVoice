import heapq
import math


import numpy as np

class Caption(object):
    def __init__(self, sentence, state, logprob, score, metadata=None):
        """Initializes the Caption.

        Args:
          sentence: List of word ids in the caption.
          state: Model state after generating the previous word.
          logprob: Log-probability of the caption.
          score: Score of the caption.
          metadata: Optional metadata associated with the partial sentence. If not
            None, a list of strings with the same length as 'sentence'.
        """
        self.sentence = sentence
        self.state = state
        self.logprob = logprob
        self.score = score
        self.metadata = metadata

    def __cmp__(self, other):
        """Compares Captions by score."""
        assert isinstance(other, Caption)
        if self.score == other.score:
            return 0
        elif self.score < other.score:
            return -1
        else:
            return 1

        # For Python 3 compatibility (__cmp__ is deprecated).

    def __lt__(self, other):
        assert isinstance(other, Caption)
        return self.score < other.score

        # Also for Python 3 compatibility.

    def __eq__(self, other):
        assert isinstance(other, Caption)
        return self.score == other.score

class PQ(object):
    def __init__(self, n):
        self.n = n
        self.data = []

    def push(self, x):
        if len(self.data) < self.n:
            heapq.heappush(self._data, x)
        else:
            heapq.heappushpop(self._data, x)

    def size(self):
        assert self._data is not None
        return len(self._data)

    def extract(self):
        data = self.data
        self.data = []
        return data

class CaptionGenerator(object):
    def __init__(self,
               model,
               vocab,
               beam_size=3,
               max_caption_length=20,
               length_normalization_factor=0.0):
        """Initializes the generator.

            Args:
              model: Object encapsulating a trained image-to-text model. Must have
                methods feed_image() and inference_step(). For example, an instance of
                InferenceWrapperBase.
              vocab: A Vocabulary object.
              beam_size: Beam size to use when generating captions.
              max_caption_length: The maximum caption length before stopping the search.
              length_normalization_factor: If != 0, a number x such that captions are
                scored by logprob/length^x, rather than logprob. This changes the
                relative scores of captions depending on their lengths. For example, if
                x > 0 then longer captions will be favored.
            """

        self.vocab = vocab
        self.model = model

        self.beam_size = beam_size
        self.max_caption_length = max_caption_length
        self.length_normalization_factor = length_normalization_factor

    def beam_search(self, sess, encoded_image):
        """Runs beam search caption generation on a single image.

            Args:
              sess: TensorFlow Session object.
              encoded_image: An encoded image string.

            Returns:
              A list of Caption sorted by descending score.
            """
        initial_state = self.model.feed_image(sess, encoded_image)

        initial_beam = Caption(sentence=[self.vocab.start_id], state=initial_state[0],
                               logprob=0.0, score=0.0, metadata=[""])

        partial_captions = PQ(self.beam_size)
        complete_captions = PQ(self.beam_size)
        partial_captions.push(initial_beam)

        for _ in range(self.max_caption_length - 1):
            partial_captions_list = list(enumerate(partial_captions.extract()))
            input_feed = np.array([c.sentence[-1] for c in partial_captions_list[1]])
            state_feed = np.array([c.state for c in partial_captions_list[1]])

            softmax, new_states, metadata = self.model.inference_step(sess, input_feed, state_feed)

            for i, partial_caption in partial_captions_list:
                word_probabilities = softmax[i]
                state = new_states[i]
                # For this partial caption, get the beam_size most probable next words.
                words_and_probs = list(enumerate(word_probabilities))
                words_and_probs.sort(key=lambda x: -x[1])
                words_and_probs = words_and_probs[0:self.beam_size]

                for w, p in words_and_probs:
                    if p < 1e-12:
                        continue  # Avoid log(0).
                    sentence = partial_caption.sentence + [w]
                    logprob = partial_caption.logprob + math.log(p)
                    score = logprob
                    if metadata:
                        metadata_list = partial_caption.metadata + [metadata[i]]
                    else:
                        metadata_list = None
                    if w == self.vocab.end_id:
                        if self.length_normalization_factor > 0:
                            score /= len(sentence) ** self.length_normalization_factor
                        beam = Caption(sentence, state, logprob, score, metadata_list)
                        complete_captions.push(beam)
                    else:
                        beam = Caption(sentence, state, logprob, score, metadata_list)
                        partial_captions.push(beam)
            if partial_captions.size() == 0:
                # We have run out of partial candidates; happens when beam_size = 1.
                break

        # If we have no complete captions then fall back to the partial captions.
        # But never output a mixture of complete and partial captions because a
        # partial caption could have a higher score than all the complete captions.
        if not complete_captions.size():
            complete_captions = partial_captions

        data = complete_captions.extract()
        data.sort(reverse=True)
        return data