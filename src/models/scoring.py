"""Numerical fitting, probabilities, and classification metrics."""

import math


def solve(a, b):
    """Solve a*x = b by Gaussian elimination (small systems only)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for i in range(n):
        p = max(range(i, n), key=lambda k: abs(m[k][i]))
        m[i], m[p] = m[p], m[i]
        for k in range(i + 1, n):
            f = m[k][i] / m[i][i]
            for j in range(i, n + 1):
                m[k][j] -= f * m[i][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def fit_logistic(xs, ys, ridge=1.0, steps=25):
    """Logistic regression by Newton's method. Returns [intercept, w1, w2, ...]."""
    d = len(xs[0]) + 1
    w = [0.0] * d
    for _ in range(steps):
        grad = [0.0] * d
        hess = [[0.0] * d for _ in range(d)]
        for x, y in zip(xs, ys):
            v = [1.0] + x
            p = 1.0 / (1.0 + math.exp(-sum(wi * vi for wi, vi in zip(w, v))))
            s = p * (1.0 - p)
            for i in range(d):
                grad[i] += (p - y) * v[i]
                hi, vi = hess[i], v[i] * s
                for j in range(i, d):
                    hi[j] += vi * v[j]
        for i in range(d):
            for j in range(i):
                hess[i][j] = hess[j][i]
            if i:  # no penalty on the intercept
                grad[i] += ridge * w[i]
                hess[i][i] += ridge
        step = solve(hess, grad)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    return w


def predict(w, x):
    return 1.0 / (1.0 + math.exp(-(w[0] + sum(wi * xi for wi, xi in zip(w[1:], x)))))


def logit(p: float, epsilon: float | None = None) -> float:
    """Log odds, with the caller's existing numerical clipping policy."""
    if epsilon is not None:
        p = min(max(p, epsilon), 1 - epsilon)
    return math.log(p / (1 - p))


def prf(flags, ys):
    tp = sum(1 for f, y in zip(flags, ys) if f and y)
    fp = sum(1 for f, y in zip(flags, ys) if f and not y)
    fn = sum(1 for f, y in zip(flags, ys) if not f and y)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1, tp, fp, fn


def best_f1_threshold(ps, ys):
    best = (0.0, 0.5)
    for t in sorted(set(ps)):
        f1 = prf([p >= t for p in ps], ys)[2]
        if f1 > best[0]:
            best = (f1, t)
    return best[1]
