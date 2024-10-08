import numpy as np

from simple_tracer import tracer


def main():
    x = np.random.rand(1024, 1024)
    y = np.random.rand(1024, 1024)
    z = np.matmul(x, y)
    print(z)

    for _ in range(100):
        z = x @ y


if __name__ == "__main__":
    with tracer("numpy_matmul.json"):
        main()
