# ========== #
#  Libraries #
# ========== #
from __future__ import print_function, division

import datetime
import os
import time
import argparse


import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from keras.backend.tensorflow_backend import set_session
from keras_preprocessing.image import img_to_array, load_img
from tqdm import tqdm

from dataset_handler import load_dataset
from model import build_generator, build_discriminator

# ================= #
#  Global Variables #
# ================= #
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

config = tf.ConfigProto()
config.gpu_options.allow_growth = True  # dynamically grow the memory used on the GPU
config.log_device_placement = True  # to log device placement (on which device the operation ran)

sess = tf.Session(config=config)
set_session(sess)  # set this TensorFlow session as the default

tf.logging.set_verbosity(tf.logging.ERROR)  # TODO: comment this line

plt.ion()

def args_handler():
    parser = argparse.ArgumentParser()
    parser.add_argument("-m", "--mode", type=str, help="Chooses program mode.")

    return parser.parse_args()

# ===== #
#  Main #
# ===== #
def train():
    # Defines Input shape
    img_rows, img_cols, channels, channels_depth = 256, 256, 3, 1

    img_shape = (img_rows, img_cols, channels)
    depth_shape = (img_rows, img_cols, channels_depth)

    # Sets Training Variables
    epochs = 300
    batch_size = 4
    sample_interval = 1

    # --------
    # Dataset
    # --------
    train_images, train_labels = load_dataset()

    # -------------------------
    # Construct Computational
    #   Graph of Generator
    # -------------------------
    optimizer = tf.keras.optimizers.Adam(0.0002, 0.5)

    # Build and compile the discriminator
    discriminator = build_discriminator(img_shape, depth_shape)
    discriminator.summary()
    discriminator.compile(loss='mse',
                          optimizer=optimizer,
                          metrics=['accuracy'])
    # Build the generator
    generator = build_generator(img_shape, channels_depth)
    generator.summary()

    # Input images and their conditioning images
    img_A = tf.keras.Input(shape=depth_shape)
    img_B = tf.keras.Input(shape=img_shape)

    # By conditioning on B generate a fake version of A
    fake_A = generator(img_B)

    # For the combined model we will only train the generator
    discriminator.trainable = False

    # Discriminators determines validity of translated images / condition pairs
    valid = discriminator([fake_A, img_B])

    combined = tf.keras.Model(inputs=[img_A, img_B], outputs=[valid, fake_A])
    combined.summary()
    combined.compile(loss=['mse', 'mae'],
                     loss_weights=[1, 100],
                     optimizer=optimizer)

    start_time = datetime.datetime.now()

    # Calculate output shape of D (PatchGAN)
    patch = int(img_rows / 2 ** 4)
    patch2 = int(img_cols / 2 ** 4)
    disc_patch = (patch, patch2, 1)

    # Adversarial loss ground truths
    valid = np.ones((batch_size,) + disc_patch)
    fake = np.zeros((batch_size,) + disc_patch)

    def sample_images():
        # os.makedirs('images/%s' % dataset_name, exist_ok=True)
        r, c = 1, 2

        # imgs_A, imgs_B = data_loader.load_data(batch_size=3, is_testing=True)
        imgs_B = load_and_scale_image(train_images[0])
        imgs_A = load_and_scale_depth(train_labels[0])
        fake_A = generator.predict(imgs_B)

        gen_imgs = np.concatenate([fake_A, imgs_A])

        # Rescale images 0 - 1
        gen_imgs = 0.5 * gen_imgs + 0.5

        titles = ['Original', 'Prediction (Translated)', 'GT']
        fig, axs = plt.subplots(r, c)

        cax0 = axs[0].imshow(np.squeeze(gen_imgs[0], axis=2) * 85.0)
        fig.colorbar(cax0, ax=axs[0])
        axs[0].set_title(titles[1])

        cax1 = axs[1].imshow(np.squeeze(gen_imgs[1], axis=2) * 85.0)
        fig.colorbar(cax1, ax=axs[1])
        axs[1].set_title(titles[2])

        plt.show()
        plt.pause(60.0)
        plt.close('all')

    def load_and_scale_image(filepath):
        image_input = img_to_array(load_img(filepath, target_size=(img_rows, img_cols), interpolation='lanczos'))
        image_input = image_input.astype(np.float32)
        image_input = np.expand_dims(image_input, axis=0)
        return (image_input / 127.5) - 1

    def load_and_scale_depth(filepath):
        image_input = Image.open(filepath)
        image_input = image_input.resize((img_cols, img_rows), Image.LANCZOS)
        image_input = np.expand_dims(image_input, axis=-1).astype(np.uint16) / 256.0
        image_input = image_input.astype(np.float32)
        image_input = np.expand_dims(image_input, axis=0)
        return (image_input / 42.5) - 1

    numSamples = len(train_images)

    for epoch in range(epochs):
        batch_start = 0
        batch_end = batch_size
        for batch in tqdm(range((len(train_images) // batch_size) + 1)):

            limit = batch_end

            if limit > numSamples:
                limit = numSamples
                batch_start = numSamples - batch_size

            imgs_B = np.concatenate(list(map(load_and_scale_image, train_images[batch_start:limit])), 0)
            imgs_A = np.concatenate(list(map(load_and_scale_depth, train_labels[batch_start:limit])), 0)

            # print(imgs_A.shape)
            # print(imgs_B.shape)

            batch_start += batch_size
            batch_end += batch_size

            # ---------------------
            #  Train Discriminator
            # ---------------------

            # Condition on B and generate a translated version
            fake_A = generator.predict(imgs_B)

            # Train the discriminators (original images = real / generated = Fake)
            d_loss_real = discriminator.train_on_batch([imgs_A, imgs_B], valid)
            d_loss_fake = discriminator.train_on_batch([fake_A, imgs_B], fake)
            d_loss = 0.5 * np.add(d_loss_real, d_loss_fake)

            # -----------------
            #  Train Generator
            # -----------------

            # Train the generators
            g_loss = combined.train_on_batch([imgs_A, imgs_B], [valid, imgs_A])

            elapsed_time = datetime.datetime.now() - start_time

            # sample_images()

        # If at save interval => save generated image samples
        if epoch % sample_interval == 0:
            generator.save_weights('weights_generator_bce.h5')
            discriminator.save_weights('weights_discriminator_bce.h5')
            combined.save_weights('weights_combined_bce.h5')

        # Plot the progress
        print("[Epoch %d/%d] [D loss: %f, acc: %3d%%] [G loss: %f] time: %s" % (epoch, epochs,
                                                                                d_loss[0], 100 * d_loss[1],
                                                                                g_loss[0],
                                                                                elapsed_time))


if __name__ == '__main__':
    args = args_handler()
    print(args)
    input('aki')
    if args.mode == 'train':
        train()
    elif args.mode == 'test':
        print("Implementar!")
    else:
        raise SystemError