# Name: 
#   Wasserstein Generative Adversarial Nets
# Desc:
#   Use Wasserstein Distance as the loss function to solve the unstablity of GAN
#   Wasserstein Distance: Also named EarthMover Distance, The energy cost of moving mound P1 to P2
#   The Discriminator in WGAN don't use sigmoid, because the normalization function has a defect that 
#   the convergence is slow at both ends of the function, and the gradient is almost 0
#       1. Entirely solve the unstablity of GAN
#       2. Mainly solve the model collapse of GAN
#       3. Have a centain target to instruct the training
#       4. No need to cost plenty of time to design the Nerual Net
# Procedure:
#
#  Real images ----------------------|
#                                    |       -----      |----> 1 (real)
#                                    | ----> | D | ---->|
#            -----                   |       --|--      |----> 0 (fake)
#  Noise --> | G | --> Fake images --|         |
#            --|--                             |
#              |<------------------------------|


from tensorflow.keras.datasets import mnist
from tensorflow.keras.layers import Input, Dense, Reshape, Flatten, Dropout
from tensorflow.keras.layers import BatchNormalization, Activation, ZeroPadding2D
from tensorflow.keras.layers import LeakyReLU
from tensorflow.keras.layers import UpSampling2D, Conv2D
from tensorflow.keras.models import Sequential, Model
from tensorflow.keras.optimizers import RMSprop

import tensorflow.keras.backend as K
import matplotlib.pyplot as plt
import sys
import os
import numpy as np


def wasserstein_loss(y_true, y_pred):
    return K.mean(y_true * y_pred)

class WGAN:
    def __init__(self, img_shape, sample_shape=(5,5), latent_dim=128, g_optimizer=RMSprop(lr=0.00005), d_optimizer=RMSprop(lr=0.00005), g_loss=wasserstein_loss, d_loss=wasserstein_loss):
        if type(img_shape) == tuple and len(img_shape) == 3:
            self.img_shape = img_shape
        else:
            print("[Error] Param 'img_shape' should be a triple set, eg. (28,28,1)")
            sys.exit(1)
        
        if type(sample_shape) == tuple and len(sample_shape) == 2:
            self.sample_shape = sample_shape
        else:
            print("[Error] Param 'sample_shape' should be a double set, eg. (5,5)")
            sys.exit(1)
        
        if type(latent_dim) == int and latent_dim > 0:
            self.latent_dim = latent_dim
        else:
            print("[Error] Param 'latent' should be a positive integer, eg. 128")
            sys.exit(1)
        
        # Following parameter and optimizer set as recommended in paper
        self.n_discriminator = 5
        self.clip_value = 0.01

        # Build and compile the discriminator
        self.discriminator = Discriminator(self.img_shape).modelling()
        self.discriminator.compile(loss=d_loss, optimizer=d_optimizer, metrics=['accuracy'])

        # Build the generator
        self.generator = Generator(self.img_shape, self.latent_dim).modelling()

        # Build the Combined (Generator + Discriminator)
        self.combined = self.combine()
        self.combined.compile(loss=g_loss, optimizer=g_optimizer)
        
    def combine(self):
        # The generator takes noise as input and generates imgs
        z = Input(shape=(self.latent_dim,))
        img = self.generator(z)

        # For the combined model we will only train the generator
        self.discriminator.trainable = False

        # The discriminator takes generated images as input and determines validity
        validity = self.discriminator(img)

        # The combined model  (stacked generator and discriminator)
        # Trains the generator to fool the discriminator
        combined = Model(z, validity)

        return combined

    def train_one_epoch(self, X_train, epoch, batch_size, valid, fake):
        # ---------------------
        #  Train Discriminator
        # ---------------------

        for _ in range(self.n_discriminator):
            # Select a random batch of images
            idx = np.random.randint(0, X_train.shape[0], batch_size)
            imgs = X_train[idx]

            # Generate noise randomly
            noise = np.random.normal(0, 1, (batch_size, self.latent_dim))

            # Generate a batch of new images
            gen_imgs = self.generator.predict(noise)

            # Train the discriminator
            d_loss_real = self.discriminator.train_on_batch(imgs, valid)
            d_loss_fake = self.discriminator.train_on_batch(gen_imgs, fake)
            d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

            # Clip discriminator weights, in order to satisfy the 1-Lipschitz condition, WGAN-GP improve here
            for l in self.discriminator.layers:
                weights = l.get_weights()
                weights = [np.clip(w, -self.clip_value, self.clip_value) for w in weights]
                l.set_weights(weights)

        # ---------------------
        #  Train Generator
        # ---------------------

        noise = np.random.normal(0, 1, (batch_size, self.latent_dim))
        # Train the generator (to have the discriminator label samples as valid)
        g_loss = self.combined.train_on_batch(noise, valid)

        # Plot the progress
        print ("%d [D loss: %f] [G loss: %f]" % (epoch, 1 - d_loss[0], 1 - g_loss))


    # Train the Models(G && D)
    def train(self, data, epochs, batch_size=128, sample_interval=200):
        X_train = data
        # Rescale -1 to 1
        X_train = (X_train.astype(np.float32) - 127.5) / 127.5
        X_train = np.expand_dims(X_train, axis=3)

        # Adversarial ground truths
        valid = np.ones((batch_size, 1))
        fake = -np.ones((batch_size, 1))

        for epoch in range(1, epochs+1):
            self.train_one_epoch(X_train, epoch, batch_size, valid, fake)

            # If at save interval => save generated image samples
            if epoch % sample_interval == 0:
                self.sample_images(epoch)

    # Generate images with Generator in current epoch
    def sample_images(self, epoch):
        # images matrix scale is r*c
        r, c = self.sample_shape
        noise = np.random.normal(0, 1, (r * c, self.latent_dim))
        gen_imgs = self.generator.predict(noise)

        # Rescale images 0 - 1
        gen_imgs = 0.5 * gen_imgs + 0.5

        samples = "images/"
        if not os.path.exists(samples):
            os.mkdir(samples)

        # Draw and Save the images
        fig, axs = plt.subplots(r, c)
        cnt = 0
        for i in range(r):
            for j in range(c):
                axs[i,j].imshow(gen_imgs[cnt, :,:,0], cmap='gray')
                axs[i,j].axis('off')
                cnt += 1
        fig.savefig("%s%d.png" % (samples, epoch))
        plt.close()

class Generator:
    def __init__(self, img_shape, latent):
        self.img_shape = img_shape
        self.latent_dim = latent

    # Build Generator Model
    def modelling(self):
        model = Sequential()

        model.add(Dense(128 * 7 * 7, activation="relu", input_dim=self.latent_dim))
        model.add(Reshape((7, 7, 128)))
        model.add(UpSampling2D())
        model.add(Conv2D(128, kernel_size=4, padding="same"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Activation("relu"))
        model.add(UpSampling2D())
        model.add(Conv2D(64, kernel_size=4, padding="same"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(Activation("relu"))
        model.add(Conv2D(self.img_shape[2], kernel_size=4, padding="same"))
        model.add(Activation("tanh"))

        model.summary()

        noise = Input(shape=(self.latent_dim,))
        img = model(noise)

        return Model(inputs=noise, outputs=img)


class Discriminator:
    def __init__(self, img_shape):
        self.img_shape = img_shape

    # Build Discriminator Model
    def modelling(self):
        model = Sequential()

        model.add(Conv2D(16, kernel_size=3, strides=2, input_shape=self.img_shape, padding="same"))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(Conv2D(32, kernel_size=3, strides=2, padding="same"))
        model.add(ZeroPadding2D(padding=((0,1),(0,1))))
        model.add(BatchNormalization(momentum=0.8))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(Conv2D(64, kernel_size=3, strides=2, padding="same"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(Conv2D(128, kernel_size=3, strides=1, padding="same"))
        model.add(BatchNormalization(momentum=0.8))
        model.add(LeakyReLU(alpha=0.2))
        model.add(Dropout(0.25))
        model.add(Flatten())
        model.add(Dense(1))

        model.summary()

        img = Input(shape=self.img_shape)
        validity = model(img)

        return Model(inputs=img, outputs=validity)


if __name__ == "__main__":
    # Load the dataset
    (X_train, _), (_, _) = mnist.load_data()
    wgan = WGAN(img_shape=(28,28,1))
    wgan.train(data=X_train, epochs=400, batch_size=32, sample_interval=400)