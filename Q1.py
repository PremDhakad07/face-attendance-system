import numpy as np
def inverse_matrix(matrix):
    return np.linalg.inv(matrix)

matrix = np.array([[1,2,3],[0,1,4],[5,6,0]])
inverse = inverse_matrix(matrix)

if inverse is not None:
    print("Inverse matrix:")
    print(inverse)
else:
    print("Matrix is not invertible")