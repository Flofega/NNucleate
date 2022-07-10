import torch
from time import time
from copy import deepcopy
import numpy as np

def train_linear(dataloader, model_t, loss_fn, optimizer, device, print_batch=1000000):
    """Performs one training epoch for a NNCV.

    :param dataloader: Wrappper for the training set.
    :type dataloader: torch.utils.data.Dataloader
    :param model_t: The network to be trained.
    :type model_t: NNCV
    :param loss_fn: Pytorch loss to be used during training.
    :type loss_fn: torch.nn._Loss
    :param optimizer: Pytorch optimizer to be used during training.
    :type optimizer: torch.optim
    :param device: Pytorch device to run the calculation on. Supports CPU and GPU (cuda).
    :type device: str
    :param print_batch: Set to recieve printed updates on the lost every print_batch batches, defaults to 1000000.
    :type print_batch: int, optional
    :return: Returns the last loss item. For easy learning curve recording. Alternatively one can use a Tensorboard.
    :rtype: float
    """
    size = len(dataloader.dataset)
    for batch, (X, y) in enumerate(dataloader):
        X, y = X.to(device), y.to(device)

        # Compute prediction error
        pred = model_t(X)
        loss = loss_fn(pred.flatten(), y)

        # Backpropagation
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if batch % print_batch == 0:
            loss, current = loss.item(), batch * len(X)
            print(f"loss: {loss:>7f} [{current:>5d}/{size:>5d}]")

    return loss.item()


def train_gnn( model, loader, n_at, optimizer, loss, device):
    """Function to perform one epoch of a GNN training.

    :param model: Graph-based model_t to be trained.
    :type model: GNNCV
    :param loader: Wrapper around a GNNTrajectory dataset.
    :type loader: torch.utils.data.Dataloader
    :param n_at: Number of nodes per frame.
    :type n_at: int
    :param optimizer: The optimizer object for the training.
    :type optimizer: torch.optim
    :param loss: Loss function for the training.
    :type loss: torch.nn._Loss
    :param device: Device that the training is performed on. (Required for GPU compatibility)
    :type device: str
    :return: Return the average loss over the epoch.
    :rtype: float
    """
    res = {"loss": 0, "counter": 0}
    for batch, (X, y, r, c) in enumerate(loader):
        model.train()
        optimizer.zero_grad()
        batch_size = len(X)
        atom_positions = X.view(-1, 3).to(device)

        row_new = r.view(-1)
        col_new = c.view(-1)
        row_new = row_new[row_new > 0]
        col_new = col_new[col_new > 0]
        j = 0
        for i in range(1, len(row_new)):
            row_new[i] += j * n_at
            col_new[i] += j * n_at

            if row_new[i - 1] > row_new[i]:
                j += 1
                row_new[i] += n_at
                col_new[i] += n_at

        edges = [row_new.long().to(device), col_new.long().to(device)]
        label = y.to(device)

        pred = model(x=atom_positions, edges=edges, n_nodes=n_at)
        loss = loss(pred, label)
        loss.backward()
        optimizer.step()

        res["loss"] += loss.item() * batch_size
        res["counter"] += batch_size

    return res["loss"] / res["counter"]


def train_perm(
    dataloader, model_t, optimizer, loss_fn, n_trans, device, print_batch=1000000
):
    """Performs one training epoch for a NNCV but the loss for each batch is not just calculated on one reference structure but a set of n_trans permutated versions of that structure.

    :param loader: Wrapper around a GNNTrajectory dataset.
    :type loader: torch.utils.data.Dataloader
    :param n_at: Number of nodes per frame.
    :type n_at: int
    :param optimizer: The optimizer object for the training.
    :type optimizer: torch.optim
    :param loss_fn: Loss function for the training.
    :type loss_fn: torch.nn._Loss
    :param n_trans: Number of permutated structures used for the loss calculations.
    :type n_trans: int
    :param device: Pytorch device to run the calculations on. Supports CPU and GPU (cuda).
    :type device: str
    :param print_batch: Set to recieve printed updates on the loss every print_batches batches, defaults to 1000000.
    :type print_batch: int, optional
    :return: Returns the last loss item. For easy learning curve recording. Alternatively one can use a Tensorboard.
    :rtype: float
    """
    size = len(dataloader.dataset)
    for batch, (X, y) in enumerate(dataloader):
        X, y = X.to(device), y.to(device)

        # Compute prediction error
        pred = model_t(X)
        loss = loss_fn(pred.flatten(), y)

        for i in range(n_trans):
            # Shuffle the tensors in the batch
            pred = model_t(X[:, torch.randperm(X.size()[1])])
            loss += loss_fn(pred.flatten(), y)

        loss /= n_trans

        # Backpropagation
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if batch % print_batch == 0:
            loss, current = loss.item(), batch * len(X)
            print(f"loss: {loss:>7f} [{current:>5d}/{size:>5d}]")

    return loss.item()


def test(dataloader, model_t, loss_fn, device):
    """Calculates the current average test set loss.

    :param dataloader: Dataloader loading the test set.
    :type dataloader: torch.utils.data.Dataloader
    :param model: Model that is being trained.
    :type model: NNCV
    :param loss_fn: Pytorch loss function.
    :type loss_fn: torch.nn._Loss
    :param device: Device that the training is performed on. (Required for GPU compatibility)
    :type device: str
    :return: Return the validation loss.
    :rtype: float
    """
    size = len(dataloader.dataset)
    num_batches = len(dataloader)
    model_t.eval()
    test_loss = 0
    with torch.no_grad():
        for X, y in dataloader:
            X, y = X.to(device), y.to(device)
            pred = model_t(X)
            test_loss += loss_fn(pred.flatten(), y).item()

    test_loss /= num_batches
    print(f"Avg. Test loss: {test_loss:>8f} \n")
    return test_loss


def test_gnn(model, loader, n_at, loss_l1, device):
    """Evaluate the test/validation error of a graph based model_t on a validation set. 

    :param model: Graph-based model_t to be trained.
    :type model: GNNCV
    :param loader: Wrapper around a GNNTrajectory dataset.
    :type loader: torch.utils.data.Dataloader
    :param n_at: Number of nodes per frame.
    :type n_at: int
    :param loss_l1: Loss function for the training.
    :type loss_l1: torch.nn._Loss
    :param device: Device that the training is performed on. (Required for GPU compatibility)
    :type device: str
    :return: Return the average loss over the epoch.
    :rtype: float
    """
    res = {'loss': 0, 'counter': 0}
    for batch, (X, y, r, c) in enumerate(loader):
        model.eval()
        batch_size = len(X)
        atom_positions = X.view(-1, 3).to(device)

        row_new = r.view(-1)
        col_new = c.view(-1)
        row_new = row_new[row_new > 0]
        col_new = col_new[col_new > 0]
        j = 0
        for i in range(1, len(row_new)):
            row_new[i] += j*n_at
            col_new[i] += j*n_at

            if row_new[i-1] > row_new[i]:
                j += 1
                row_new[i] += n_at
                col_new[i] += n_at

        edges = [row_new.long().to(device), col_new.long().to(device)]
        label = y.to(device)
        pred = model(x=atom_positions, edges=edges, n_nodes = n_at)
        #print(label, pred)
        loss = loss_l1(pred, label)

        res['loss'] += loss.item() * batch_size
        res['counter'] += batch_size

    return res['loss'] / res['counter']


def early_stopping_gnn(model_t, train_loader, val_loader, n_at, optimizer, loss, device, test_freq=1):
    """Train a graph-based model according to the early-stopping approach.
    In early stopping a model is trained until the validation error (approximation for the generalisation error) worsens for the first time to prevent overfitting.
    Once an increase in the validation error is detected for the first time th eloop is exited and the model-state from the *previous* validation is returned.

    :param model_t: The graph-based model hat is to be optimised.
    :type model_t: GNNCV
    :param train_loader: Wrapper around the training set for the model optimisation.
    :type train_loader: torch.utils.data.Dataloader
    :param val_loader: Wrapper around the validation set for the model optimisation.
    :type val_loader: torch.utils.data.Dataloader
    :param n_at: Number of nodes in the graph (Number of atoms or molecules).
    :type n_at: int
    :param optimizer: Optimizer to be used for the optimisation.
    :type optimizer: torch.optim
    :param loss: Loss function to be used for the optimisation.
    :type loss: torch.nn._Loss
    :param device: Device that the training is performed on. (Required for GPU compatibility)
    :type device: str    
    :param test_freq: The number of epochs after which the model should be evaluated. A lower number is more accurate and costs more but is reccomended for big datasets, defaults to 1
    :type test_freq: int, optional
    :return: This function returns the optimised model and the history of test and training errors over the course of the convergence.
    :rtype: GNNCV, list of float, list of float
    """
    conv_tr = []
    conv_te = []
    epoch=1
    old_val_e = 100000000000
    old_model = deepcopy(model_t)

    while True:
        print("Current epoch: ", epoch)
        t = time()
        l = train_gnn(model_t, train_loader, n_at, optimizer, loss, device)
        conv_tr.append(l)
        print(f"training loss: %.4f" % l)
        print(f"time per epoch: %.2f s" % (time()-t))

        if epoch % test_freq == 0:
            val_e = test_gnn(model_t, val_loader, n_at, loss, device)
            conv_te.append(val_e)
            print(f"val loss: %.4f" % val_e)
            if val_e > old_val_e:
                model_t = old_model
                break
            old_val_e = val_e


            old_model = deepcopy(model_t)
        epoch += 1

    return model_t, conv_tr, conv_te


def evaluate_model_gnn(model, dataloader, n_at, device):
    """Helper function that evaluates a model on a training set and calculates some properies for the generation of performance scatter plots.

    :param model: The model that is to be evaluated.
    :type model: GNNCV
    :param dataloader: Wrapper around the dataset that the model is supposed to be evaluated on.
    :type dataloader: torch.utils.data.Dataloader
    :param n_at: Number of nodes in the graph of each frame. (Number of atoms or molecules)
    :type n_at: int
    :param device: Device that the training is performed on. (Required for GPU compatibility)
    :type device: str
    :return: Returns the prediction of the model on each frame, the corresponding true values, the root mean square error of the predictions and the r2 correlation coefficient.
    :rtype: List of float, List of float, float, float
    """
    preds = []
    ys = []
    for batch, (X, y, r, c) in enumerate(dataloader):
        model.eval()
        #optimizer.zero_grad()
        batch_size = len(X)
        atom_positions = X.view(-1, 3).to(device)
        row_new = r.view(-1)
        col_new = c.view(-1)
        row_new = row_new[row_new > 0]
        col_new = col_new[col_new > 0]
        j = 0
        for i in range(1, len(row_new)):
            row_new[i] += j*n_at
            col_new[i] += j*n_at
            if row_new[i-1] > row_new[i]:
                j += 1
                row_new[i] += n_at
                col_new[i] += n_at

        edges = [row_new.long().to(device), col_new.long().to(device)]
        pred = model(x=atom_positions, edges=edges, n_nodes = n_at)
        [ys.append(ref.item()) for ref in y]
        [preds.append(pre.item()) for pre in pred]

    rmse = np.mean((np.array(preds) - np.array(ys))**2)**0.5
    r2 = np.corrcoef(preds, ys)[0, 1]
    
    return preds, ys, rmse, r2