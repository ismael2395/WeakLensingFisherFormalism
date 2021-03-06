"""This module contains functions necessary to produce statistical results of
the fisher formalism from a given galaxy.
"""

import copy
import math

import numpy as np

from . import gparameters
from . import images
from .. import defaults


def get_snr(img, var_noise):
    return np.sqrt(np.sum(img.array ** 2) / var_noise)


class Fisher(object):
    """Produce fisher object (containing fisher analysis) for a given set of
    galaxy parameters.

    Given a galaxy image and the appropriate parameters that describe it,
    (in the form of :class:`analysis.gparameters.GParameters` object) will produce a fisher object that
    contains the analysis of it using the Fisher Formalism.
    
    NOTE: The matrices are in dictionary form, use the function matrix_to_numpy_array() to change them
    to a matrix that is ordered according to param_names. 

        Args:
            g_parameters(:class:`GParameters`): String point to the directory 
                                                specified by the user.
            image_renderer(:class:`ImageRenderer`): Object used to render image of galaxy. 
            snr(float): Value S/N ratio to use in the analysis. 

        Attributes:
            image_renderer_partials(:class:`analysis.gparameters.ImageRenderer`): Object used to render
            images of partial derivatives. 
            image(:class:`Galsim.Image`): Dictionary whose keys are the ids of each of the
                galaxies specified in galaxies.csv, and that map to another dictionary that can be taken in by :func:`analysis.gparameters.get_galaxy_model`
            var_noise(float): Variance of noise of given S/N . 
            steps(dict): Dictionary containing the step size used when 
                calculating partial derivatives. 
            param_names(list): A list containing the keys of fit_params
                in a desirable order.
            num_params(int): Number of parameters specified for the galaxy. 
            num_galaxies(int): Number of galaxies specified.
            derivatives_images(dict): Dictionary containing np.array(s) that represent the 
                derivative of the galaxy(ies) with respect to each parameter. 
            second_derivatives_images(dict): Dictionary containing np.array(s) that represent the 
                second derivatives of the galaxy(ies) with respect to its parameters.  
            fisher_matrix_images(dict): Dictionary containing np.array(s) that represent the 
                fisher matrix images of the galaxy(ies) with respect to its parameters.
            fisher_matrix(dict): Dictionary containing fisher matrix elements. 
            covariance_matrix(dict): Dictionary containing covariance matrix elements. 
            correlation_matrix(dict): Dictionary containing correlation matrix elements. 
            bias_matrix_images(dict): Dictionary containing bias matrix image elements.
            bias_matrix(dict): Dictionary containing bias matrix elements.
            bias_images(dict): Dictionary containing bias images elements.
            biases(dict): Dictionary containing biases
    """

    def __init__(self, g_parameters, image_renderer, snr, var_noise=None):
        self.g_parameters = g_parameters
        self.snr = snr
        self.model = gparameters.get_galaxies_models(g_parameters=self.g_parameters)
        self.image_renderer = image_renderer
        self.num_galaxies = self.g_parameters.num_galaxies

        # we do not want to mask or crop the images used to obtain the partials.
        self.image_renderer_partials = images.ImageRenderer(stamp=self.image_renderer.stamp)
        self.image = self.image_renderer.get_image(self.model)

        if var_noise is None:
            if self.num_galaxies == 1:
                _, self.var_noise = images.add_noise(self.image, self.snr, 0)
            else:
                # obtain the image of only the first galaxy
                model_galaxy1 = gparameters.get_galaxy_model(self.g_parameters.id_params['1'])
                image_galaxy1 = self.image_renderer.get_image(model_galaxy1)
                _, self.var_noise = images.add_noise(image_galaxy1, snr)

                # also obtain the snr for the rest of the galaxies and put them in a list
                self.snrs = []
                self.snrs.append(self.snr)  # the first entry is the snr of the first galaxy
                for id_gal in list(self.g_parameters.id_params.keys())[1:]:
                    model_galaxy = gparameters.get_galaxy_model(self.g_parameters.id_params[id_gal])
                    image_galaxy = self.image_renderer.get_image(model_galaxy)
                    self.snrs.append(get_snr(image_galaxy, self.var_noise))

        else:
            self.var_noise = var_noise

        self.steps = defaults.get_steps(self.g_parameters, self.image_renderer)
        self.param_names = g_parameters.ordered_fit_names
        self.num_params = len(self.param_names)

        self.derivatives_images = self.get_derivative_images()
        self.second_derivatives_images = self.get_second_derivatives_images()
        self.fisher_matrix_images = self.get_fisher_matrix_images()
        self.fisher_matrix = self.get_fisher_matrix()
        self.covariance_matrix = self.get_covariance_matrix()
        self.correlation_matrix = self.get_correlation_matrix()
        self.bias_matrix_images = self.get_bias_matrix_images()
        self.bias_matrix = self.get_bias_matrix()
        self.bias_images = self.get_bias_images()
        self.biases = self.get_biases()

        self.fisher_condition_number = self.get_fisher_condition_number()

    def matrix_to_numpy_array(self, matrix):
        """Convert matrix dictionary to a numpy array."""
        array = np.zeros([self.num_params, self.num_params])
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]
                element = matrix[param_i, param_j]
                array[i][j] = element
        return array

    def numpy_array_to_matrix(self, array):
        """Convert numpy array to matrix dictionary."""
        matrix = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]
                matrix[param_i, param_j] = array[i][j]
        return matrix

    def get_derivative_images(self):
        """Return images of the partial derivatives of the galaxy.

        The partial differentiation includes each of the different parameters
        that describe the galaxy.
        """
        partials_images = {}
        for i in range(self.num_params):
            param = self.param_names[i]
            params_up = copy.deepcopy(self.g_parameters.params)
            params_up[param] += self.steps[param]
            params_down = copy.deepcopy(self.g_parameters.params)
            params_down[param] -= self.steps[param]
            gal_up = gparameters.get_galaxies_models(params_up)
            gal_down = gparameters.get_galaxies_models(params_down)
            img_up = self.image_renderer_partials.get_image(gal_up)
            img_down = self.image_renderer_partials.get_image(gal_down)
            partials_images[param] = ((img_up - img_down) / (2 * self.steps[param])).array
        return partials_images

    def get_second_derivatives_images(self):
        """Return the images for the second derivatives of the given galaxy."""
        secondDs_gal = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]

                params_iup_jup = copy.deepcopy(self.g_parameters.params)
                params_iup_jup[param_i] += self.steps[param_i]
                params_iup_jup[param_j] += self.steps[param_j]

                params_idown_jup = copy.deepcopy(self.g_parameters.params)
                params_idown_jup[param_i] -= self.steps[param_i]
                params_idown_jup[param_j] += self.steps[param_j]

                params_iup_jdown = copy.deepcopy(self.g_parameters.params)
                params_iup_jdown[param_i] += self.steps[param_i]
                params_iup_jdown[param_j] -= self.steps[param_j]

                params_idown_jdown = copy.deepcopy(self.g_parameters.params)
                params_idown_jdown[param_i] -= self.steps[param_i]
                params_idown_jdown[param_j] -= self.steps[param_j]

                gal_iup_jup = gparameters.get_galaxies_models(params_iup_jup)
                gal_idown_jup = gparameters.get_galaxies_models(params_idown_jup)
                gal_iup_jdown = gparameters.get_galaxies_models(params_iup_jdown)
                gal_idown_jdown = gparameters.get_galaxies_models(params_idown_jdown)

                img_iup_jup = self.image_renderer_partials.get_image(gal_iup_jup)
                img_idown_jup = self.image_renderer_partials.get_image(gal_idown_jup)
                img_iup_jdown = self.image_renderer_partials.get_image(gal_iup_jdown)
                img_idown_jdown = self.image_renderer_partials.get_image(gal_idown_jdown)

                secondDs_gal[param_i, param_j] = ((img_iup_jup + img_idown_jdown -
                                                   img_idown_jup - img_iup_jdown) /
                                                  (4 * self.steps[param_i] * self.steps[param_j])).array

        return secondDs_gal

    def get_fisher_matrix_images(self):
        """Produce images of fisher matrix)."""
        FisherM_images = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]
                derivative1 = self.derivatives_images[param_i]
                derivative2 = self.derivatives_images[param_j]
                FisherM_images[param_i, param_j] = (
                        derivative1 * derivative2 / self.var_noise)
        return FisherM_images

    def get_fisher_matrix(self):
        """Calculate the actual values of the fisher matrix."""
        FisherM = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]
                FisherM[param_i, param_j] = (
                    self.fisher_matrix_images[param_i, param_j].sum())
        return FisherM

    def get_covariance_matrix(self):
        """Calculate the covariance matrix by inverting fisher matrix."""
        fisher_array = self.matrix_to_numpy_array(self.fisher_matrix)
        covariance_array = np.linalg.inv(fisher_array)
        return self.numpy_array_to_matrix(covariance_array)

    def get_correlation_matrix(self):
        """Calculate correlation matrix from the covariance matrix."""
        correlation_matrix = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                param_i = self.param_names[i]
                param_j = self.param_names[j]
                sigma_ij = self.covariance_matrix[param_i, param_j]
                sigma_i = math.sqrt(self.covariance_matrix[param_i, param_i])
                sigma_j = math.sqrt(self.covariance_matrix[param_j, param_j])
                correlation_matrix[param_i, param_j] = (sigma_ij /
                                                        (sigma_i * sigma_j))

        return correlation_matrix

    def get_bias_matrix_images(self):
        """Produce images of each element of the bias matrix."""
        BiasM_images = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                for k in range(self.num_params):
                    param_i = self.param_names[i]
                    param_j = self.param_names[j]
                    param_k = self.param_names[k]
                    BiasM_images[param_i, param_j, param_k] = (
                            self.derivatives_images[param_i] *
                            self.second_derivatives_images[param_j, param_k] /
                            self.var_noise)

        return BiasM_images

    def get_bias_matrix(self):
        """Return bias matrix from the images of the bias matrix"""
        BiasM = {}
        for i in range(self.num_params):
            for j in range(self.num_params):
                for k in range(self.num_params):
                    param_i = self.param_names[i]
                    param_j = self.param_names[j]
                    param_k = self.param_names[k]
                    BiasM[param_i, param_j, param_k] = self.bias_matrix_images[
                        param_i, param_j, param_k].sum()
        return BiasM

    def get_bias_images(self):
        """Construct the bias of each parameter per pixel."""
        bias_images = {}
        for i in range(self.num_params):
            summation = 0
            for j in range(self.num_params):
                for k in range(self.num_params):
                    for l in range(self.num_params):
                        param_i = self.param_names[i]
                        param_j = self.param_names[j]
                        param_k = self.param_names[k]
                        param_l = self.param_names[l]
                        summation += (self.covariance_matrix[param_i, param_j] *
                                      self.covariance_matrix[param_k, param_l] *
                                      self.bias_matrix_images[param_j, param_k,
                                                              param_l])
            bias_images[self.param_names[i]] = (-.5) * summation
        return bias_images

    def get_biases(self):
        """Return the value of the bias of each parameter in vector form."""
        return {
            self.param_names[i]: self.bias_images[self.param_names[i]].sum()
            for i in range(self.num_params)
        }

    def get_fisher_condition_number(self):
        """The condition number will give a sense of how singular the matrix tends to be."""
        fisher_array = self.matrix_to_numpy_array(self.fisher_matrix)
        return np.linalg.cond(fisher_array)
