import numpy as np
import matplotlib.pyplot as plt
from matplotlib import ticker
from scipy.stats import describe
import scipy.cluster.hierarchy as shc
import seaborn as sns
from sklearn.cluster import AgglomerativeClustering
from sklearn.decomposition import PCA
import pandas as pd


def show_hist(
    data, xlabel: str, title: str, log_scale: bool = False, ylabel: str = "Frequency"
):
    if log_scale:
        data = np.log1p(data)

    # Create a histogram
    plt.hist(data, bins=30, density=True, alpha=0.7, color="blue", edgecolor="black")

    # Add labels and title
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title + " converted to log-scale" if log_scale else "")

    plt.show()


def show_statistics(data):
    describe_result = describe(data)

    print(f"Summary")
    print(f"Min: {describe_result.minmax[0]}, Max: {describe_result.minmax[1]}")
    print(f"Mean: {describe_result.mean}")
    print(f"Var: {describe_result.variance}")


# Taken from https://matplotlib.org/stable/gallery/images_contours_and_fields/image_annotated_heatmap.html


def heatmap(
    data, row_labels, col_labels, ax=None, cbar_kw=None, cbarlabel="", **kwargs
):
    """
    Create a heatmap from a numpy array and two lists of labels.

    Parameters
    ----------
    data
        A 2D numpy array of shape (M, N).
    row_labels
        A list or array of length M with the labels for the rows.
    col_labels
        A list or array of length N with the labels for the columns.
    ax
        A `matplotlib.axes.Axes` instance to which the heatmap is plotted.  If
        not provided, use current axes or create a new one.  Optional.
    cbar_kw
        A dictionary with arguments to `matplotlib.Figure.colorbar`.  Optional.
    cbarlabel
        The label for the colorbar.  Optional.
    **kwargs
        All other arguments are forwarded to `imshow`.
    """

    if ax is None:
        ax = plt.gca()

    if cbar_kw is None:
        cbar_kw = {}

    # Plot the heatmap
    im = ax.imshow(data, **kwargs)

    # Create colorbar
    cbar = ax.figure.colorbar(im, ax=ax, **cbar_kw)
    cbar.ax.set_ylabel(cbarlabel, rotation=-90, va="bottom")

    # Show all ticks and label them with the respective list entries.
    ax.set_xticks(np.arange(data.shape[1]), labels=col_labels)
    ax.set_yticks(np.arange(data.shape[0]), labels=row_labels)

    # Let the horizontal axes labeling appear on top.
    ax.tick_params(top=True, bottom=False, labeltop=True, labelbottom=False)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=-30, ha="right", rotation_mode="anchor")

    # Turn spines off and create white grid.
    ax.spines[:].set_visible(False)

    ax.set_xticks(np.arange(data.shape[1] + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(data.shape[0] + 1) - 0.5, minor=True)
    ax.grid(which="minor", color="w", linestyle="-", linewidth=3)
    ax.tick_params(which="minor", bottom=False, left=False)

    return im, cbar


def annotate_heatmap(
    im,
    data=None,
    valfmt="{x:.2f}",
    textcolors=("black", "white"),
    threshold=None,
    **textkw,
):
    """
    A function to annotate a heatmap.

    Parameters
    ----------
    im
        The AxesImage to be labeled.
    data
        Data used to annotate.  If None, the image's data is used.  Optional.
    valfmt
        The format of the annotations inside the heatmap.  This should either
        use the string format method, e.g. "$ {x:.2f}", or be a
        `matplotlib.ticker.Formatter`.  Optional.
    textcolors
        A pair of colors.  The first is used for values below a threshold,
        the second for those above.  Optional.
    threshold
        Value in data units according to which the colors from textcolors are
        applied.  If None (the default) uses the middle of the colormap as
        separation.  Optional.
    **kwargs
        All other arguments are forwarded to each call to `text` used to create
        the text labels.
    """

    if not isinstance(data, (list, np.ndarray)):
        data = im.get_array()

    # Normalize the threshold to the images color range.
    if threshold is not None:
        threshold = im.norm(threshold)
    else:
        threshold = im.norm(data.max()) / 2.0

    # Set default alignment to center, but allow it to be
    # overwritten by textkw.
    kw = dict(horizontalalignment="center", verticalalignment="center")
    kw.update(textkw)

    # Get the formatter in case a string is supplied
    if isinstance(valfmt, str):
        valfmt = ticker.StrMethodFormatter(valfmt)

    # Loop over the data and create a `Text` for each "pixel".
    # Change the text's color depending on the data.
    texts = []
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            kw.update(color=textcolors[int(im.norm(data[i, j]) > threshold)])
            text = im.axes.text(j, i, valfmt(data[i, j], None), **kw)
            texts.append(text)

    return texts


def show_heatmap(
    data,
    title: str,
    cbar_title: str = "Spike Power (mean of squared voltage)",
):
    fig, ax = plt.subplots()

    im, cbar = heatmap(
        data,
        range(0, data.shape[0]),
        range(0, data.shape[1]),
        ax=ax,
        cmap="YlGn",
        cbarlabel=cbar_title,
    )
    # texts = annotate_heatmap(im, valfmt="{x:.1f}")
    plt.title(title)
    plt.show()


def pca_most_valuable_features(pca, data_percentage):
    return np.where(pca.explained_variance_ratio_.cumsum() >= data_percentage)[0][0]


def show_clusters(data, num_cluster: int, samples: int):
    # PCA components
    pca = PCA(n_components=128)
    pca.fit_transform(data)
    index_95 = pca_most_valuable_features(pca, 0.95)

    pca = PCA(n_components=index_95)
    pcs = pca.fit_transform(data)

    index_50 = pca_most_valuable_features(pca, 0.50)

    print(f"PCA\n50%: {index_50}, 95%: {index_95}")

    select_features = min(5, index_50)

    sns.set(style="ticks", color_codes=True)
    sns.pairplot(
        pd.DataFrame(pcs[:, :select_features]).sample(n=samples, random_state=1),
        markers=".",
    )
    plt.show()

    pcs_frame = pd.DataFrame(pcs[:, :index_95]).sample(n=samples, random_state=1)

    clusters = shc.linkage(pcs_frame, method="ward")
    shc.dendrogram(Z=clusters)
    plt.show()
    agg_model = AgglomerativeClustering(
        n_clusters=num_cluster, affinity="euclidean", linkage="ward"
    )
    agg_model.fit(pcs_frame)

    pcs_frame[select_features + 1] = agg_model.labels_

    sns.set(style="ticks", color_codes=True)
    sns.pairplot(
        pcs_frame.iloc[:, : select_features + 2],
        hue=select_features + 1,
        palette="husl",
        markers=".",
    )
    plt.show()


def write_feature_graph(
    data: pd.Series, name: str, col: int, save_path: str, show_plot: bool = False
):
    plt.figure()
    data.plot(kind="line")
    plt.ylabel(f"Rolling mean of {name}")
    plt.xlabel("Bin number")
    plt.title("Rolling mean of voltages over time")
    plt.savefig(save_path + f"/{name}_over_time_{col}.png")
    if show_plot:
        plt.show()
    plt.close()


def write_graph_per_feature(
    data: pd.DataFrame, name: str, save_path: str, show_features: list[int] = []
):
    # Groups by time bin
    mean_per_time_bin = data.groupby(level=1).mean()
    rolling_mean = mean_per_time_bin.rolling(window=5, min_periods=1).mean()

    for i, col in enumerate(rolling_mean.columns):
        write_feature_graph(rolling_mean[col], name, col, save_path, i in show_features)
