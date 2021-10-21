"""

Backporting Flag and Intflag from python 3.8 enum.py into python 2.7
for use in Ginkgo edX.

Source is apparently at https://github.com/python/cpython/blob/3.8/Lib/enum.py
and the license terms at https://github.com/python/cpython/blob/main/LICENSE
state that the code is open source, that the license is GPL compatible, and
that "All Python licenses, unlike the GPL, let you distribute a modified version
without making your changes open source."

The code below was modifed for use in this Xblock, was based on code
we had in /usr/lib/python3.8/enum.py and has local changes we made
in order to get it what we need to work in Ginkgo (Python 2.7).

Our modified version of this code can be used under the same terms as
the original Python source of enum.py.

"""
from enum import Enum 
class Flag(Enum):
    """
    Support for flags
    """

    def __contains__(self, other):
        """
        Returns True if self has at least the same flags set as other.
        """
        if not isinstance(other, self.__class__):
            raise TypeError(
                "unsupported operand type(s) for 'in': '%s' and '%s'" % (
                    type(other).__qualname__, self.__class__.__qualname__))
        return other._value_ & self._value_ == other._value_

    def __repr__(self):
        cls = self.__class__
        if self._name_ is not None:
            return '<%s.%s: %r>' % (cls.__name__, self._name_, self._value_)
        members, uncovered = _decompose(cls, self._value_)
        return '<%s.%s: %r>' % (
                cls.__name__,
                '|'.join([str(m._name_ or m._value_) for m in members]),
                self._value_,
                )

    def __str__(self):
        cls = self.__class__
        if self._name_ is not None:
            return '%s.%s' % (cls.__name__, self._name_)
        members, uncovered = _decompose(cls, self._value_)
        if len(members) == 1 and members[0]._name_ is None:
            return '%s.%r' % (cls.__name__, members[0]._value_)
        else:
            return '%s.%s' % (
                    cls.__name__,
                    '|'.join([str(m._name_ or m._value_) for m in members]),
                    )

    def __bool__(self):
        return bool(self._value_)

    def __or__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.__class__(self._value_ | other._value_)

    def __and__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.__class__(self._value_ & other._value_)

    def __xor__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.__class__(self._value_ ^ other._value_)

    def __invert__(self):
        members, uncovered = _decompose(self.__class__, self._value_)
        inverted = self.__class__(0)
        for m in self.__class__:
            if m not in members and not (m._value_ & self._value_):
                inverted = inverted | m
        return self.__class__(inverted)


class IntFlag(int, Flag):
    """
    Support for integer-based Flags
    """

    def __or__(self, other):
        if not isinstance(other, (self.__class__, int)):
            return NotImplemented
        result = self.__class__(self._value_ | self.__class__(other)._value_)
        return result

    def __and__(self, other):
        if not isinstance(other, (self.__class__, int)):
            return NotImplemented
        return self.__class__(self._value_ & self.__class__(other)._value_)

    def __xor__(self, other):
        if not isinstance(other, (self.__class__, int)):
            return NotImplemented
        return self.__class__(self._value_ ^ self.__class__(other)._value_)

    __ror__ = __or__
    __rand__ = __and__
    __rxor__ = __xor__

    def __invert__(self):
        result = self.__class__(~self._value_)
        return result