class A:
    def __add__(self, other):
        return self


a = A()
b = A()
c = a + b
