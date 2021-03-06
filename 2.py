import os

# disable x
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
import torch.nn.functional as F
from torch.nn import DataParallel
from torch.utils.data import ConcatDataset, DataLoader, Subset
from tqdm import tqdm

from config import o
from data import BSD, BSD3000, Levin, Sun
from model import ModelStack, ModelStage
from util import crop, log, npsnr, show, mean, isnan, npsnr_align_max, load, change_key, center_crop

o.device = "cuda" if torch.cuda.is_available() else "cpu"
print("use " + o.device)

# m:model to train, p:pre models
def train(m, p=None):
    d = DataLoader(BSD3000(), o.batch_size, num_workers=o.num_workers, shuffle=True)
    optimizer = torch.optim.Adam(m.parameters(), lr=o.lr)
    iter_num = len(d)
    num = 0
    losss = []
    mse = torch.nn.MSELoss()
    stage = 1 if not p else p.stage + 1
    for epoch in range(o.epoch):
        for i in tqdm(d):
            g, y, k, s = [x.to(o.device) for x in i]
            k = k.flip(1, 2)
            x = y
            if p:
                with torch.no_grad():
                    x = p([x, y, k, s])
            optimizer.zero_grad()
            out = m([x, y, k, s])
            log("out", out)
            out = crop(out, k)
            loss = npsnr(out, g)
            loss.backward()
            optimizer.step()
            losss.append(loss.detach().item())
            assert not isnan(losss[-1])
            print("stage", stage, "epoch", epoch + 1)
            log("loss", mean(losss[-5:]))
            num += 1
            if num > (o.epoch * iter_num - 4):
                # if num % 6 == 1:
                show(
                    torch.cat((crop(y, k)[0, 0], g[0, 0], out[0, 0]), 1),
                    # save=f"save/{stage:02}{epoch:02}.png",
                )
    plt.clf()
    plt.plot([i + 1 for i in range(len(losss))], losss)
    plt.xlabel("batch")
    plt.ylabel("loss")
    plt.title(f"{iter_num} iter x {o.epoch} epoch")
    plt.savefig(f"save/{stage:02}loss.png")


# greedy train the i stage
def greedy(stage=1):
    p = None
    m = DataParallel(ModelStack(1)).to(o.device)
    if stage > 1:
        p = DataParallel(ModelStack(stage - 1)).to(o.device)
        load(p, torch.load("save/01-10g.tar"))
        p.stage = stage - 1
    train(m, p)
    # concat and save
    a = change_key(m.module.m[0].state_dict(), lambda x: f"m.{stage-1}." + x)
    if p:
        a.update(p.module.state_dict())
    torch.save(a, f"save/01-10g.tar")


# sun
def test(m):
    m.eval()
    with torch.no_grad():
        d = DataLoader(Sun(), 1)
        losss = []
        for i in tqdm(d):
            g, y, k, s = [x.to(o.device) for x in i]
            out = m([y, y, k, s])
            out = crop(out, k)
            out = center_crop(out, *g.shape[-2:])
            loss = npsnr(out, g)
            losss.append(-loss.detach().item())
            log("psnr", losss[-1])
            show(torch.cat((center_crop(y, *g.shape[-2:])[0, 0], g[0, 0], out[0, 0]), 1))
        log("psnr avg", sum(losss) / len(losss))


# Levin
# def test(m):
#     m.eval()
#     with torch.no_grad():
#         d = DataLoader(Levin(), 1)
#         losss = []
#         for i in tqdm(d):
#             g, y, k, s = [x.to(o.device) for x in i]
#             out = m([y, y, k, s])
#             g = crop(g, k)
#             out = crop(out, k)
#             g = crop(g, k)
#             out = crop(out, k)
#             loss, out, left, top = npsnr_align_max(g, out)
#             losss.append(-loss.detach().item())
#             log("psnr", losss[-1])
#             # show(torch.cat((center_crop(y, *g.shape[-2:])[0, 0], g[0, 0], out[0, 0]), 1))
#         log("psnr avg", sum(losss) / len(losss))


if __name__ == "__main__":
    # m = DataParallel(ModelStack(1)).to(o.device)
    # load(m, torch.load(f"save/01-10g.tar"))
    # test(m)
    for i in range(1, 11):
        print("greedy train stage " + str(i))
        greedy(i)
