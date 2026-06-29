In twenty-seventeen, one paper quietly rewired artificial intelligence. Its title was a flex — Attention Is All You Need.

---

Back then, translation models had three problems. They were sequential — one word at a time. They couldn't be parallelized. And long-range connections faded.

---

The Transformer threw all of that out. Instead, every word looks at every other word, all at once. They called it self-attention.

---

The whole idea fits in one line. Attention is the softmax of Q times K transpose, scaled by the square root of d k, times V. Queries ask, keys answer, and values get blended by how well they match.

---

Run that eight times in parallel — eight heads, each catching a different kind of relationship — then concatenate the results.

---

But with no recurrence, the model has no sense of order. So they stamp in position using sine and cosine waves of different frequencies.

---

Stack it six layers deep — an encoder and a decoder — where every layer is just attention, plus a feed-forward network, wrapped in residual connections.

---

Then they ran it on English to German translation, against the best models in the world.

---

Twenty-eight point four BLEU — two full points past the previous best — at a third of the compute, trained in just three and a half days.

---

That architecture became GPT. It became BERT. It became the backbone of modern AI. Turns out, attention really was all you needed.