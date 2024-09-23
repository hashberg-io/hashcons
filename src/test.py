from flyweight import InstanceStore
from typing import ClassVar, Literal
from typing_extensions import Self

class MyFrac:

    _store: ClassVar[InstanceStore] = InstanceStore()

    __num: int
    __den: int

    def __new__(cls, num: int, den: int) -> Self:
        instance_key = (num, den) # instance key derived from constructor args
        with MyFrac._store.instance(cls, instance_key) as self:
            if self is None: # if no instance with given key exists
                # 1. Validate constructor arguments:
                if den == 0:
                    raise ZeroDivisionError()
                # 2. Create the new instance:
                self = super().__new__(cls)
                # 3. Set instance attributes:
                self.__num = num
                self.__den = den
                # 4. Register the instance in the store:
                MyFrac._store.register(self)
            return self


    def __getnewargs__(self) -> tuple[int, int]:
        return (self.__num, self.__den)

    def __getstate__(self) -> Literal[None]:
        return None

