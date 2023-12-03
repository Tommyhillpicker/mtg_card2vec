"""
word2vec-like embedding portion of the model, responsible for capturing the statistical associations between cards.

For the purposes of generating this embedding, the "context window" for a particular sample is simply a 17Lands draft
deck. Training pairs are subsampled combinations of each card that appear within the draft deck.
"""

import torch
import torch.nn as nn
import torch.optim as optim

from torch.nn.functional import one_hot
from torch.utils.data import DataLoader, TensorDataset
from evals.card2vec_downstream_tasks import Card2VecEmbeddingEval


class Card2VecFFNN(nn.Module):
    """
    Implementation of the Card2Vec embedding model. Based on the Feedforward Neural Net Language Model (FFNN) defined
    in Mikolov et al. 2013, Efficient Estimation of Word Representations in Vector Space. In the this model, the
    weights of a single hidden layer are trained based on a Softmax regression

    Attributes:
        set_size (int)      : Size of the "vocabulary" (i.e. number of cards in the set being trained on)
        embedding_dim (int) : Number of neurons in the hidden layer of the embedding -- a hyperparameter
    """
    def __init__(self, set_size, embedding_dim):
        super(Card2VecFFNN, self).__init__()
        self.embedding = nn.Embedding(set_size, embedding_dim)
        self.hidden = nn.Linear(embedding_dim, set_size)
        self.softmax = nn.Softmax(dim=1)

    def forward(self, target):
        embed_target = self.embedding(target)
        out = self.softmax(self.hidden(embed_target))
        return out


def train_card2vec_embedding(set_size, embedding_dim,              # vocab size and embedding dim
                             training_corpus, card_labels,         # training set of training pairs
                             epochs, learning_rate, batch_size):   # training / optimizer hyperparameters
    """
    Creates an instance of a Card2VecFFN model, loads data from the supplied training_corpus, and learns card embeddings

    Arguments:
        set_size (int)           : size of the training 'vocabulary' (i.e. len of the one-hot encodings)
        embedding_dim (int)      : embedding size, hyperparameter
        training_corpus (Tensor) : (N, 2, D) large Tensor of training samples
        card_labels (tuple)      : tuple of 2 dicts containing name labels for the one-hot embedding
        epochs (int)             : number of training epochs, hyperparameter
        learning_rate (float)    : SGD learning rate, hyperparameter
        batch_size (int)         : training batch size, hyperparameter

    Return:
        card_embeddings : return embedding weights after training
    """
    # Init model and optimizer
    model = Card2VecFFNN(set_size, embedding_dim)
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.CrossEntropyLoss()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    # Get one-hot name labels -- set Tensors to proper device / dtype
    name_to_1h, _ = card_labels

    # Target cards (i.e. card vector being learned per iteration)
    targets = training_corpus[:, 0].to(device)

    # Context cards -- Need to one-hot encode contexts for use in CE Loss
    contexts = one_hot(training_corpus[:, 1].to(dtype=torch.int64)).to(device, dtype=torch.float)

    dataset = TensorDataset(targets, contexts)
    data_loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        total_loss = 0.0

        for it, batch in enumerate(data_loader):
            # Split targets and contexts -- convert one-hot representations to appropriate types for calcs
            targets = batch[0]
            contexts = batch[1]

            optimizer.zero_grad()
            out = model(targets)

            loss = criterion(out, contexts)
            loss.backward()  # Backprop
            optimizer.step()

            total_loss += loss.item()

            # print(f"Batch {it} loss: {loss.item()}")

        # Evaluate some downstream tasks each epoch

        eval = Card2VecEmbeddingEval(model.embedding.weight.data)
        close_dist, close_sim = eval.eval_distances(
            torch.tensor(name_to_1h["Imperial Oath"]).to(device),
            torch.tensor(name_to_1h["Imperial Subduer"]).to(device)  # Should be similar
        )

        far_dist, far_sim = eval.eval_distances(
            torch.tensor(name_to_1h["Imperial Oath"]).to(device),
            torch.tensor(name_to_1h["Skyswimmer Koi"]).to(device)    # Should be less similar
        )

        print(f"Clo calcs -- dist: {close_dist:.5f}, sim: {close_sim:.5f}")
        print(f"Far calcs -- dist: {far_dist:.5f}, sim: {far_sim:.5f}")

        print(f"Epoch {epoch} -- Total Loss: {total_loss}\n")

    return model.embedding.weight.data