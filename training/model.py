"""
ThoughtLink — EEGNet Model
Compact convolutional neural network for EEG classification.
"""
import torch
import torch.nn as nn


class EEGNet(nn.Module):
    """EEGNet architecture for EEG-based BCI classification.

    Input: (batch, 1, 500, 6) — 1s window, 6 channels at 500Hz

    Architecture:
        1. Temporal Conv2d → captures frequency patterns
        2. Depthwise Conv2d → learns spatial filters
        3. Separable Conv2d → combines temporal-spatial features
        4. Linear classifier
    """

    def __init__(self, num_classes=5, channels=6, samples=500,
                 temporal_filters=16, spatial_multiplier=2,
                 dropout_rate=0.25):
        super().__init__()

        spatial_filters = temporal_filters * spatial_multiplier  # 32

        # Block 1: Temporal + Depthwise Spatial
        self.temporal_conv = nn.Conv2d(1, temporal_filters, (64, 1),
                                       padding=(32, 0), bias=False)
        self.depthwise_conv = nn.Conv2d(temporal_filters, spatial_filters,
                                         (1, channels), groups=temporal_filters,
                                         bias=False)
        self.bn1 = nn.BatchNorm2d(spatial_filters)
        self.elu1 = nn.ELU()
        self.pool1 = nn.AvgPool2d((4, 1))
        self.drop1 = nn.Dropout(dropout_rate)

        # Block 2: Separable Convolution
        self.separable_depth = nn.Conv2d(spatial_filters, spatial_filters,
                                          (16, 1), padding=(8, 0),
                                          groups=spatial_filters, bias=False)
        self.separable_point = nn.Conv2d(spatial_filters, spatial_filters,
                                          (1, 1), bias=False)
        self.bn2 = nn.BatchNorm2d(spatial_filters)
        self.elu2 = nn.ELU()
        self.pool2 = nn.AvgPool2d((8, 1))
        self.drop2 = nn.Dropout(dropout_rate)

        # Determine flat size dynamically
        self._flat_size = self._get_flat_size(channels, samples)

        # Classifier
        self.classifier = nn.Linear(self._flat_size, num_classes)

    def _get_flat_size(self, channels, samples):
        """Compute flattened size via dummy forward pass."""
        x = torch.zeros(1, 1, samples, channels)
        x = self._forward_features(x)
        return x.shape[1]

    def _forward_features(self, x):
        # Block 1
        x = self.temporal_conv(x)
        x = self.depthwise_conv(x)
        x = self.bn1(x)
        x = self.elu1(x)
        x = self.pool1(x)
        x = self.drop1(x)

        # Block 2
        x = self.separable_depth(x)
        x = self.separable_point(x)
        x = self.bn2(x)
        x = self.elu2(x)
        x = self.pool2(x)
        x = self.drop2(x)

        x = x.flatten(1)
        return x

    def forward(self, x):
        x = self._forward_features(x)
        x = self.classifier(x)
        return x


def count_parameters(model):
    """Count trainable parameters."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == "__main__":
    # Test model creation
    for n_classes, name in [(2, "Binary"), (5, "5-Class")]:
        model = EEGNet(num_classes=n_classes)
        dummy = torch.randn(4, 1, 500, 6)
        out = model(dummy)
        print(f"{name} EEGNet: {count_parameters(model)} params, "
              f"input={dummy.shape} -> output={out.shape}")
