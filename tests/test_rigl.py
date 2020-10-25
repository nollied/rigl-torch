import torch

from rigl_torch.RigL import RigLScheduler


# set up environment
torch.manual_seed(1)
device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')

# hyperparameters
arch = 'resnet50'
image_dimensionality = (3, 224, 224)
num_classes = 1000
max_iters = 6
T_end = int(max_iters * 0.75)
delta = 2
dense_allocation = 0.1
criterion = torch.nn.functional.cross_entropy


def get_dummy_dataloader():
    X = torch.rand((max_iters, *image_dimensionality))
    T = (torch.rand(max_iters) * num_classes).long()
    dataset = torch.utils.data.TensorDataset(X, T)
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=2)
    return dataloader


def get_new_scheduler(static_topo=False):
    model = torch.hub.load('pytorch/vision:v0.6.0', arch, pretrained=False).to(device)
    if torch.cuda.is_available() and torch.cuda.device_count() > 1:
        model = torch.nn.DataParallel(model)
    optimizer = torch.optim.SGD(model.parameters(), 0.1, momentum=0.9)
    scheduler = RigLScheduler(model, optimizer, dense_allocation=dense_allocation, T_end=T_end, delta=delta, static_topo=static_topo)
    print(model)
    print(scheduler)
    return scheduler


def assert_actual_sparsity_is_valid(scheduler):
    for l, (W, target_S, N, mask) in enumerate(zip(scheduler.W, scheduler.S, scheduler.N, scheduler.backward_masks)):
        target_zeros = int(target_S * N)
        actual_zeros = torch.sum(W == 0).item()
        print('----- layer %i ------' % l)
        print('target_zeros', target_zeros)
        print('actual_zeros', actual_zeros)
        print('mask_sum', torch.sum(mask).item())
        print('mask_shape', mask.shape)
        print('w_shape', W.shape)
        print('sum_of_nonzeros', torch.sum(W[mask]).item())
        sum_of_zeros = torch.sum(W[mask == 0]).item()
        print('sum_of_zeros', sum_of_zeros)
        print('num_of_zeros that are NOT actually zeros', torch.sum(W[mask == 0] != 0).item())
        print('avg_of_zeros', torch.mean(W[mask == 0]).item())
        assert sum_of_zeros == 0


def assert_sparse_elements_remain_zeros(static_topo):
    scheduler = get_new_scheduler(static_topo)
    model = scheduler.model
    optimizer = scheduler.optimizer
    dataloader = get_dummy_dataloader()

    model.train()
    for i, (X, T) in enumerate(dataloader):
        Y = model(X.to(device))
        loss = criterion(Y, T.to(device))
        loss.backward()

        is_rigl_step = True
        if scheduler():
            is_rigl_step = False
            optimizer.step()

        print('iteration: %i\trigl steps completed: %i\tis_rigl_step=%s' % (i, scheduler.rigl_steps, str(is_rigl_step)))
        assert_actual_sparsity_is_valid(scheduler)


def assert_sparse_momentum_remain_zeros(static_topo):
    scheduler = get_new_scheduler(static_topo)
    model = scheduler.model
    optimizer = scheduler.optimizer
    dataloader = get_dummy_dataloader()

    model.train()
    for i, (X, T) in enumerate(dataloader):
        Y = model(X.to(device))
        loss = criterion(Y, T.to(device))
        loss.backward()

        is_rigl_step = True
        if scheduler():
            is_rigl_step = False
            optimizer.step()

        print('iteration: %i\trigl steps completed: %i\tis_rigl_step=%s' % (i, scheduler.rigl_steps, str(is_rigl_step)))
        
        # check momentum
        for l, (w, mask) in enumerate(zip(scheduler.W, scheduler.backward_masks)):
            param_state = optimizer.state[w]
            assert 'momentum_buffer' in param_state
            buf = param_state['momentum_buffer']
            sum_zeros = torch.sum(buf[mask == 0]).item()
            print('layer %i' % l)
            assert sum_zeros == 0


class TestRigLScheduler:
    def test_initial_sparsity(self):
        scheduler = get_new_scheduler()
        assert_actual_sparsity_is_valid(scheduler)

    def test_sparse_momentum_remain_zeros_STATIC_TOPO(self):
        assert_sparse_momentum_remain_zeros(True)

    def test_sparse_momentum_remain_zeros_RIGL_TOPO(self):
        assert_sparse_momentum_remain_zeros(False)

    def test_sparse_elements_remain_zeros_STATIC_TOPO(self):
        assert_sparse_elements_remain_zeros(True)

    def test_sparse_elements_remain_zeros_RIGL_TOPO(self):
        assert_sparse_elements_remain_zeros(False)
