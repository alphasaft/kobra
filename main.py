from hypnosis.interfaces import Installer ; Installer.install_all()
from interface.csv.data import content  # noqa
from interface.json.file import content  # noqa


print(type(content))


# TODO : IDEE RANDOM MAIS PAS MAL : Un language de programmation pour m'aider pour mes maths.
# Style
"""

#theory set
#using set-theory-base

Notation A[X] where A is a Ring => SetOfAlmostNullFamiliesOf<A>On<I>
Using A[X] sets X to UndeterminedOf<A>
Notation P' where A is a Ring, where P is in A[X] => DerivativePolynomOf<P>

Given K a Field
Given P of K[X]

Display P'


SOME EXPLANATIONS OF HOW IT WILL WORK

'#theory set' sets the theory to sets' theory ; a theory is defined by builtin constructs and laws, the axioms
'#using [...]' is an import

Then it gets more complicated

'Notation A[X] where A is a Ring => SetOfAlmostNullFamiliesOf<A>'
tells the program that whenever it encounters something like A[X], it will check that A is a Ring
or something that inherits from a Ring, then replace the whole expression with SetOfAlmostNullFamiliesOf<A>

'Using A[X] sets X to UndeterminedOf<A>'
means that when the A[X] notation is encountered, then unless it was already/will be defined, X is automatically
set to UndeterminedOf<A>

"Notation P' where A is a Ring, where P is in A[X] => DerivativePolynomOf<P>"
will probably be one hell of a show when implementing it, as it goes :
whenever the notation P' is encountered, if there exists A a Ring so that P belongs to A[X], then return
DerivativePolynomOf<P>, else I don't know how to interpret it.


'Given K a Field' instantiate a Field named K
'Given P of K[X]' picks a element of K[X], with no particularity, and sets P to it

"Display P'" asks the program to display the expression of P' when given the expression of P.
Here we are confrontated to quite a big problem : how should the program know how to represent P' ? And
what about P, because it wasn't explictly announced how to properly represent a polynom.    

The last question is : how should a program know how to solve problems ? I think the answer is : It doesn't know.
Programs are done to help us, not to do the whole thing for us, so I think that although it won't solve the whole Ramis
in 1 or 2 seconds, it can be really helpful and is worth the time I'll need to build it.

"""
