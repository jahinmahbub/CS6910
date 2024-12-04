import rasterio
import pandas as pd
import numpy as np
import os
from rasterio.transform import Affine, xy
from pyproj import Transformer
import matplotlib.pyplot as plt


def adjust_transform_for_zoom(transform, zoom_factor):
    """Adjust the affine transform to apply a zoom."""
    if zoom_factor == 1.0:
        return transform  # No zooming needed

    # Adjust the scaling components (a and e) of the affine transform
    scaled_transform = transform * Affine.scale(zoom_factor)
    print(f"Adjusted transform for zoom factor {zoom_factor}: {scaled_transform}")
    return scaled_transform


def process_geotiff_and_gt(geotiff_file, gt_csv_file, date, zoom_factor):
    # Load GeoTIFF
    with rasterio.open(geotiff_file) as dataset:
        print(f"Processing {date}...")
        print("GeoTIFF CRS:", dataset.crs)
        bounds = dataset.bounds  # Original GeoTIFF bounds
        print("Original GeoTIFF bounds:", bounds)

        # Apply zoom adjustment to the affine transform
        transform = adjust_transform_for_zoom(dataset.transform, zoom_factor)

        # Compute the adjusted bounds for reference
        adjusted_bounds = rasterio.windows.bounds(
            rasterio.windows.Window(0, 0, dataset.width, dataset.height), transform
        )
        print("Adjusted GeoTIFF bounds:", adjusted_bounds)

        # Load GT CSV
        gt_data = pd.read_csv(gt_csv_file)
        gt_data.columns = gt_data.columns.str.strip()  # Strip whitespace

        # Get GeoTIFF CRS dynamically
        geotiff_crs = dataset.crs.to_string()
        wgs84_crs = "EPSG:4326"  # CRS for longitude/latitude

        # Create a transformer
        transformer = Transformer.from_crs(wgs84_crs, geotiff_crs, always_xy=True)

        # Transform longitude/latitude to UTM
        gt_data['UTM_X'], gt_data['UTM_Y'] = transformer.transform(gt_data['Longitude'], gt_data['Latitude'])

        # Prepare training data
        training_data = []

        for _, row in gt_data.iterrows():
            utm_x, utm_y = row['UTM_X'], row['UTM_Y']

            # Ensure UTM coordinates are within the adjusted GeoTIFF bounds
            if not (adjusted_bounds[0] <= utm_x <= adjusted_bounds[2] and  # Use tuple indexing
                    adjusted_bounds[1] <= utm_y <= adjusted_bounds[3]):
                print(f"Out of bounds: UTM_X {utm_x}, UTM_Y {utm_y}")
                continue

            # Convert UTM to pixel coordinates
            pixel_row, pixel_col = ~transform * (utm_x, utm_y)
            pixel_row, pixel_col = int(round(pixel_row)), int(round(pixel_col))

            # Ensure pixel coordinates are within the image dimensions
            if 0 <= pixel_row < dataset.height and 0 <= pixel_col < dataset.width:
                try:
                    # Extract RGB values
                    red = dataset.read(1)[pixel_row, pixel_col]
                    green = dataset.read(2)[pixel_row, pixel_col]
                    blue = dataset.read(3)[pixel_row, pixel_col]

                    # Append to training data
                    training_data.append({
                        'Date': date,
                        'Pixel Row': pixel_row,
                        'Pixel Col': pixel_col,
                        'Red': red,
                        'Green': green,
                        'Blue': blue,
                        'Chlorophyll': row['Chlorophyll'],
                        'Plant Health': row['Plant health']
                    })
                except IndexError:
                    print(f"IndexError for pixel coordinates: Row {pixel_row}, Col {pixel_col}")
            else:
                print(f"Out of bounds: Pixel Row {pixel_row}, Pixel Col {pixel_col}")

    return pd.DataFrame(training_data)

def create_training_dataset(geotiff_dir, gt_csv_dir, dates, zoom_factor=1.0):
    combined_data = []

    for date in dates:
        geotiff_file = os.path.join(geotiff_dir, f"{date}.tif")
        gt_csv_file = os.path.join(gt_csv_dir, f"{date}.csv")

        print(f"Processing data for {date}...")
        training_data = process_geotiff_and_gt(geotiff_file, gt_csv_file, date, zoom_factor)
        combined_data.append(training_data)

    return pd.concat(combined_data, ignore_index=True)


# Directories for GeoTIFF and GT CSV files
geotiff_directory = 'C:/Users/Jahin Catalan Mahbub/My Drive (mzahin.zm@gmail.com)/CPP Canvas/CS6910RA/MLMODELPY/RGB_GeoTiffs'  # Path to GeoTIFF files
gt_csv_directory = 'C:/Users/Jahin Catalan Mahbub/My Drive (mzahin.zm@gmail.com)/CPP Canvas/CS6910RA/StrawberryNDVI_ChlorophyllData_Cristobal/'  # Path to GT CSV files

# Dates to process
dates_to_process = ["09.20.2024", "10.04.2024", "10.11.2024"]

# Define zoom factor (e.g., zoom in by 1.1x)
zoom_factor = 1.001  # Adjust this value to zoom in or out

# Create training dataset with the zoom factor
training_dataset = create_training_dataset(
    geotiff_directory, gt_csv_directory, dates_to_process, zoom_factor=zoom_factor
)

# Data cleaning and preprocessing
# Remove rows with zero RGB values
training_dataset = training_dataset[
    (training_dataset['Red'] != 0) &
    (training_dataset['Green'] != 0) &
    (training_dataset['Blue'] != 0)
]

# Remove rows with missing target labels
training_dataset = training_dataset.dropna(subset=['Plant Health'])

# Normalize RGB values
training_dataset[['Red', 'Green', 'Blue']] /= 255.0

# Save the cleaned dataset
output_path = 'Training.Data/cleaned_training_data.csv'
os.makedirs(os.path.dirname(output_path), exist_ok=True)  # Ensure directory exists
training_dataset.to_csv(output_path, index=False)
print(f"Cleaned training data saved to {output_path}")

# Debugging Statistics
total_points = len(training_dataset) + training_dataset['Pixel Col'].isna().sum()
valid_points = len(training_dataset)
out_of_bounds_points = total_points - valid_points
print(f"Total points: {total_points}, Valid points: {valid_points}, Out of bounds: {out_of_bounds_points}")
print(f"Percentage of valid points: {valid_points / total_points * 100:.2f}%")

# Visualization of valid points
example_geotiff_file = os.path.join(geotiff_directory, "09.20.2024.tif")
with rasterio.open(example_geotiff_file) as dataset:
    plt.imshow(dataset.read(1), cmap='gray')  # Display the first band
    plt.scatter(
        training_dataset['Pixel Col'], training_dataset['Pixel Row'],
        c='red', s=1, label='Valid Points'
    )
    plt.legend()
    plt.title("09.20.2024 Valid Points on GeoTIFF")
    plt.show()
    
# Visualization of valid points
example_geotiff_file = os.path.join(geotiff_directory, "10.04.2024.tif")
with rasterio.open(example_geotiff_file) as dataset:
    plt.imshow(dataset.read(1), cmap='gray')  # Display the first band
    plt.scatter(
        training_dataset['Pixel Col'], training_dataset['Pixel Row'],
        c='red', s=1, label='Valid Points'
    )
    plt.legend()
    plt.title("10.04.2024 Valid Points on GeoTIFF")
    plt.show()
# Visualization of valid points
example_geotiff_file = os.path.join(geotiff_directory, "10.11.2024.tif")
with rasterio.open(example_geotiff_file) as dataset:
    plt.imshow(dataset.read(1), cmap='gray')  # Display the first band
    plt.scatter(
        training_dataset['Pixel Col'], training_dataset['Pixel Row'],
        c='red', s=1, label='Valid Points'
    )
    plt.legend()
    plt.title("10.11.2024 Valid Points on GeoTIFF")
    plt.show()