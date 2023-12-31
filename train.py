from modelRoPE import *

if __name__ == '__main__':

    from torch.optim import AdamW
    from torch.optim.lr_scheduler import OneCycleLR

    import matplotlib.pyplot as plt

    import os

    device = torch.device('cuda')
    torch.backends.cuda.sdp_kernel(enable_flash=True, enable_math=True, enable_mem_efficient=True)
    # torch.backends.cudnn.benchmark = True
    # torch.set_float32_matmul_precision('high')

    context_length = 128
    embed_dim = 128
    n_head = 4
    n_layer = 2
    batch_size = 64
    accumulate = 256 // batch_size
    lr = 3e-4
    weight_decay = 1e-1
    dropout = 0.1

    file_bn = "shakespeare"

    books = Books('shakespeare.txt')
    vocab = Vocab()
    
    train_set = BooksDataset(context_length, books, vocab, train=True)
    val_set = BooksDataset(context_length, books, vocab, train=False)

    train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True, drop_last=True, pin_memory=True, num_workers=8)
    val_loader = DataLoader(val_set, batch_size=batch_size, shuffle=False, drop_last=False, pin_memory=True, num_workers=8)

    steps = len(train_loader) // accumulate

    model=LLM(vocab, context_length, embed_dim, n_head, n_layer, dropout).to(device)
    model_compile = torch.compile(model)

    params = [p for p in model_compile.parameters() if p.requires_grad]
    optim_groups = [
        {'params': [p for p in params if p.dim() >= 2], 'weight_decay': weight_decay},
        {'params': [p for p in params if p.dim() <  2], 'weight_decay': 0.0}
    ]

    optimizer = AdamW(optim_groups, lr=lr, betas=(0.9, 0.99))
    scheduler = OneCycleLR(optimizer, max_lr=lr, total_steps=steps, pct_start=0.1)

    print(f"Statistics")
    print(f"---------------------------")
    print(f"Vocab          {f'{len(vocab):,}':>12}")
    print(f"Tokens         {f'{len(train_set.data):,}':>12s}")
    print(f"---------------------------")
    print(f"Batch Size     {f'{batch_size:,}':>12}")
    print(f"Accumulate     {f'{accumulate:,}':>12}")
    print(f"Context Length {f'{context_length:,}':>12}")
    print(f"---------------------------")
    print(f"Parameters     {f'{model_compile.num_parameters:,}':>12}")
    print(f"Buffers        {f'{model_compile.num_buffers:,}':>12}")
    print(f"Footprint      {f'{(model_compile.num_parameters + model_compile.num_buffers) * 32 * 1.25e-10:.2f} GB':>12}")
    print(f"---------------------------")

    nlls = model_compile.fit(train_loader, optimizer, scheduler, steps, accumulate, device)
    plt.figure(figsize=(8, 4))
    plt.plot(nlls)
    plt.title("Training Loss over Time")
    plt.xlabel("step")
    plt.ylabel("nll")

    i = 1
    while os.path.exists(f"{file_bn}{i}.png"):
        i += 1
    file_bni = f"{file_bn}{i}"
    
    plt.savefig(f"{file_bni}.png")

    nll = model_compile.evaluate_loss(val_loader, device)
    print(f"---------------------")
    print(f"Validation NLL {f'{nll:.2f}':>6}")
    print(f"---------------------")

    device = torch.device('cpu')
    model = model.to(device)

    torch.save(model.state_dict(), f"{file_bni}.pt")

    import inspect
    with open("logs.txt", "a") as file:
        file.write(f"model_file:{os.path.basename(inspect.getfile(LLM))}, train_nll:{nlls[-1]}, eval_nll:{nll}\n")

    
    