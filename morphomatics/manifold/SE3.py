################################################################################
#                                                                              #
#   This file is part of the Morphomatics library                              #
#       see https://github.com/morphomatics/morphomatics                       #
#                                                                              #
#   Copyright (C) 2024 Zuse Institute Berlin                                   #
#                                                                              #
#   Morphomatics is distributed under the terms of the ZIB Academic License.   #
#       see $MORPHOMATICS/LICENSE                                              #
#                                                                              #
################################################################################

import jax
import jax.numpy as jnp

from morphomatics.manifold import Manifold, Connection, LieGroup, SO3, GLpn
from morphomatics.manifold.SO3 import logm as SO3_logm, expm as SO3_expm

class SE3(Manifold):
    """Returns the product manifold SE(3)^k, i.e., a product of k rigid body motions.

     manifold = SE3(k)

     Elements of SE(3)^k are represented as arrays of size kx4x4 where every 4x4 slice are homogeneous coordinates of an
     element of SE(3), i.e., the upper-left 3x3 block is the rotational part, the upper-right 3x1 part is the
     translational part, and the lower row is [0 0 0 1]. Tangent vectors, consequently, follow the same ‘layout‘.

     To improve efficiency, tangent vectors are always represented in the Lie Algebra.
     """

    def __init__(self, k=1, structure='AffineGroup'):
        if k == 1:
            name = 'Rigid motions'
        elif k > 1:
            name = 'Special Euclidean group SE(3)^{k}'.format(k=k)
        else:
            raise RuntimeError("k must be an integer no less than 1.")

        self._k = k
        self._SO = SO3(k)

        dimension = 6 * self._k
        point_shape = [self._k, 4, 4]
        super().__init__(name, dimension, point_shape)

        if structure:
            getattr(self, f'init{structure}Structure')()

    def initAffineGroupStructure(self):
        """
        Instantiate SE(3)^k with standard Lie group structure and canonical Cartan-Shouten connection.
        """
        structure = SE3.AffineGroupStructure(self)
        self._connec = structure
        self._group = structure

    @property
    def k(self):
        return self._k

    def rand(self, key: jax.random.KeyArray):
        k1, k2 = jax.random.split(key, 2)
        return jnp.zeros(self.point_shape)                   \
            .at[:, :3, :3].set(self._SO.rand(k1))             \
            .at[:, :3, 3].set(jax.random.normal(k2, (self._k, 3))) \
            .at[:, 3, 3].set(1)

    def randvec(self, P, key: jax.random.KeyArray):
        k1, k2 = jax.random.split(key, 2)
        return jnp.zeros(self.point_shape)                       \
            .at[:, :3, :3].set(self._SO.randvec(P[:, :3, :3], k1))  \
            .at[:, :3, 3].set(jax.random.normal(k2, (self._k, 3)))

    def zerovec(self):
        return jnp.zeros(self.point_shape)

    def proj(self, P, X):
        raise NotImplementedError('This function has not been implemented yet.')

    class AffineGroupStructure(Connection, LieGroup):
        """
        Standard (product) Lie group structure on SE(3)^k. The connection used is the canonical Cartan-Shouten
        connection.
        """

        def __init__(self, M):
            """
            Constructor.
            """
            self._M = M
            # SE(3) is subgroup of GL+(4) -> use methods of the latter
            self._GLp4 = GLpn(n=4, k=M.k, structure='AffineGroup')

        def __str__(self):
            return "SE3(k)-affine group structure"

        def lefttrans(self, P, S):
            """Left-translation of P by S"""
            return self._GLp4.group.lefttrans(P, S)

        def righttrans(self, P, S):
            """Right translation of P by S.
            """
            return self._GLp4.group.righttrans(P, S)

        def dleft(self, P, X):
            """Derivative of the left translation by P at the identity applied to the tangent vector X.
            """
            return self._GLp4.group.dleft(P, X)

        def dright(self, P, X):
            """Derivative of the right translation by P at the identity applied to the tangent vector X.
            """
            return self._GLp4.group.dright(P, X)

        def dleft_inv(self, P, X):
            """Derivative of the left translation by P^{-1} at f applied to the tangent vector X.
            """
            return self._GLp4.group.dleft_inv(P, X)

        def dright_inv(self, P, X):
            """Derivative of the right translation by P^{-1} at f applied to the tangent vector X.
            """
            return self._GLp4.group.dright_inv(P, X)

        def inverse(self, P):
            """Inverse map of the Lie group.
            """
            Rt = jnp.einsum('...ij->...ji', P[:, :3, :3])
            return P.at[:, :3, :3].set(Rt) \
                .at[:, :3, 3].set(jnp.einsum('...ij,...j', -Rt, P[:, :3, 3]))
            # return self._GLp4.group.inverse(P)

        def coords(self, X):
            """Coordinate map for the tangent space at the identity."""
            x123 = jnp.stack((X[:, 0, 1], X[:, 0, 2], X[:, 1, 2])) * 2**.5
            x456 = X[:, :3, 3].transpose()
            x = jnp.concatenate((x123, x456), axis=0)
            return x.reshape((-1, 1), order='F')

        def bracket(self, X, Y):
            """Lie bracket in Lie algebra."""
            return self._GLp4.group.bracket(X, Y)

        def adjrep(self, P, X):
            """Adjoint representation of P applied to the tangent vector X at the identity.
            """
            return self._GLp4.group.adjrep(P, X)

        def retr(self, R, X):
            return self.exp(R, X)

        def exp(self,  *argv):
            """Computes the Lie-theoretic and connection exponential map
            (depending on signature, i.e. whether footpoint is given as well)
            """
            return jax.lax.cond(len(argv) == 1,
                                lambda A: A[-1],
                                lambda A: jnp.einsum('...ij,...jk', A[-1], A[0]),
                                (argv[0], expm(argv[-1])))

        def log(self, *argv):
            """Computes the Lie-theoretic and connection logarithm map
            (depending on signature, i.e. whether footpoint is given as well)
            """
            return logm(jax.lax.cond(len(argv) == 1,
                                     lambda A: A[-1],
                                     lambda A: jnp.einsum('...ij,...jk', A[-1], self.inverse(A[0])),
                                     argv))

        def curvature_tensor(self, p, X, Y, Z):
            """Evaluates the curvature tensor R of the connection at p on the vectors X, Y, Z. With nabla_X Y denoting
            the covariant derivative of Y in direction X and [] being the Lie bracket, the convention
                R(X,Y)Z = (nabla_X nabla_Y) Z - (nabla_Y nabla_X) Z - nabla_[X,Y] Z
            is used.
            """
            raise NotImplementedError('This function has not been implemented yet.')

        @property
        def identity(self):
            """Identity element of SE(3)^k"""
            return jnp.tile(jnp.eye(4), (self._M.k, 1, 1))

        def transp(self, P, S, X):
            """Parallel transport for SE(3)^k.
            :param P: element of SE(3)^k
            :param S: element of SE(3)^k
            :param X: tangent vector at P
            :return: parallel transport of X at S
            """
            raise NotImplementedError('This function has not been implemented yet.')

        def pairmean(self, P, S):
            return self.exp(P, 0.5 * self.log(P, S))

        def jacobiField(self, P, S, t, X):
            raise NotImplementedError('This function has not been implemented yet.')


def logm(P):
    """
    Blanco, J. L. (2010). A tutorial on SE(3) transformation parameterizations and on-manifold optimization.
    University of Malaga, Tech. Rep, 3, 6.
    """
    w = SO3_logm(P[:, :3, :3])

    theta2 = .5 * jnp.sum(w ** 2, axis=(-1, -2))
    theta = jnp.sqrt(theta2 + jnp.finfo(jnp.float64).eps)

    Vinv = jnp.eye(3) - .5 * w + jnp.where(theta < 1e-6, 1/12 + theta2/720 + theta2**2/30240,
                                           (1 - jnp.cos(.5 * theta) / jnp.sinc(.5 * theta / jnp.pi)) / theta2) * (w @ w)

    return P.at[:, :3, :3].set(w) \
               .at[:, :3, 3].set(jnp.einsum('...ij,...j', Vinv, P[:, :3, 3])) \
               .at[:, 3, 3].set(0)


def expm(X):
    """
    Blanco, J. L. (2010). A tutorial on SE(3) transformation parameterizations and on-manifold optimization.
    University of Malaga, Tech. Rep, 3, 6.
    """
    R = SO3_expm(X[:, :3, :3])

    theta2 = .5 * jnp.sum(X[:, :3, :3] ** 2, axis=(-1,-2))
    theta = jnp.sqrt(theta2 + jnp.finfo(jnp.float64).eps)

    V = jnp.eye(3) \
        + jnp.where(theta < 1e-6, .5 - theta2/24 + theta2**2/720, (1.0 - jnp.cos(theta)) / theta2) * X[:, :3, :3] \
        + jnp.where(theta < 1e-6, 1/6 - theta2/120 + theta2**2/5040, (theta - jnp.sin(theta)) / (theta2 * theta)) \
        * (X[:, :3, :3] @ X[:, :3, :3])

    return X.at[:, :3, :3].set(R) \
               .at[:, :3, 3].set(jnp.einsum('...ij,...j', V, X[:, :3, 3])) \
               .at[:, 3, 3].set(1)
