import streamlit as st
import folium
import ee
from streamlit.components.v1 import html

# Initialize Earth Engine
ee.Authenticate()
ee.Initialize(project='ee-yashaswidarga')

def get_buffered_aoi(center_lon, center_lat, radius_km):
    # Create a point geometry from the selected coordinates
    point = ee.Geometry.Point([center_lon, center_lat])
    # Create a buffered geometry
    buffer = point.buffer(radius_km * 1000)  # Convert km to meters
    return buffer

def enhanced_lee_filter(image):
    # Define the kernel
    weights = ee.Kernel.square(radius=1)  # Use a kernel radius of 1 pixel
    
    # Calculate the mean and variance
    mean = image.reduceNeighborhood(
        reducer=ee.Reducer.mean(),
        kernel=weights
    )
    variance = image.reduceNeighborhood(
        reducer=ee.Reducer.variance(),
        kernel=weights
    )
    
    # Calculate b coefficient
    overall_variance = variance.add(1e-6)  # Avoid division by zero
    b = variance.divide(overall_variance)
    
    # Apply the filter
    result = mean.add(b.multiply(image.subtract(mean)))
    return result

def boxcar_filter(image):
    kernel = ee.Kernel.square(radius=1)  # Define kernel size
    return image.convolve(kernel)

def temporal_median(collection, start_date, end_date):
    filtered = collection.filterDate(start_date, end_date)
    median_image = filtered.median()
    return median_image

def load_image_collection(aoi, start_date, end_date):
    collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .filterBounds(aoi)
    
    return temporal_median(collection, start_date, end_date)

def process_images(aoi):
    try:
        # Load images for two different periods
        image1 = load_image_collection(aoi, '2023-01-01', '2023-01-15')
        image2 = load_image_collection(aoi, '2023-07-01', '2023-07-15')

        # Apply filters
        image1_filtered = enhanced_lee_filter(image1)
        image2_filtered = enhanced_lee_filter(image2)
        image1_boxcar = boxcar_filter(image1_filtered)
        image2_boxcar = boxcar_filter(image2_filtered)

        # Mask the images to the buffered AOI
        mask = ee.Image.constant(1).clip(aoi)
        image1_boxcar = image1_boxcar.updateMask(mask)
        image2_boxcar = image2_boxcar.updateMask(mask)

        # Calculate the difference
        diff = image2_boxcar.subtract(image1_boxcar).abs()

        # Thresholding to detect changes
        threshold = 0.1
        changes = diff.gt(threshold)

        return image1_boxcar, image2_boxcar, diff, changes
    
    except Exception as e:
        print(f"Error processing images: {e}")
        return None, None, None, None

def main():
    st.title("Interactive Map with Change Detection")

    # Create a Folium map object
    folium_map = folium.Map(location=[20, 77], zoom_start=5)

    # Add ClickForMarker functionality to Folium map
    click_marker = folium.ClickForMarker(popup='Click here to select a point')
    click_marker.add_to(folium_map)

    # Add a layer control to switch between layers
    folium.LayerControl().add_to(folium_map)

    # Render the Folium map to HTML
    map_html = folium_map.repr_html()

    st.write("Click on the map to select a point and set the buffer radius.")
    st.components.v1.html(map_html, width=700, height=500)

    with st.form("buffer_form"):
        radius_km = st.number_input("Buffer Radius (km):", value=10)  # Buffer radius input
        submitted = st.form_submit_button("Apply")

        if submitted:
            # Retrieve the coordinates from the click event
            # Note: This code assumes a fixed location for demonstration purposes
            center_lat = 20.0
            center_lon = 77.0

            # Create the buffered AOI
            aoi = get_buffered_aoi(center_lon, center_lat, radius_km)

            # Process images for change detection
            image1_boxcar, image2_boxcar, diff, changes = process_images(aoi)

            if image1_boxcar and image2_boxcar and diff:
                # Define visualization parameters
                vis_params = {'min': -25, 'max': 0}
                diff_vis_params = {'min': 0, 'max': 10}

                # Get the Map ID for the images
                map_id_image1 = ee.Image(image1_boxcar).getMapId(vis_params)
                map_id_image2 = ee.Image(image2_boxcar).getMapId(vis_params)
                map_id_diff = ee.Image(diff).getMapId(diff_vis_params)

                # Create a new Folium map with the updated data
                updated_map = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                folium.TileLayer(
                    tiles=map_id_image1['tile_fetcher'].url_format,
                    attr='Map data © Google',
                    overlay=True,
                    name='Sentinel-1 Image 1 (Filtered & Boxcar)'
                ).add_to(updated_map)
                folium.TileLayer(
                    tiles=map_id_image2['tile_fetcher'].url_format,
                    attr='Map data © Google',
                    overlay=True,
                    name='Sentinel-1 Image 2 (Filtered & Boxcar)'
                ).add_to(updated_map)
                folium.TileLayer(
                    tiles=map_id_diff['tile_fetcher'].url_format,
                    attr='Map data © Google',
                    overlay=True,
                    name='Difference Image'
                ).add_to(updated_map)

                # Convert the buffered area to GeoJSON format
                geojson_buffer = ee.FeatureCollection([ee.Feature(aoi)]).getInfo()
                
                # Add the buffer layer to the map
                folium.GeoJson(
                    data=geojson_buffer,
                    style_function=lambda x: {'color': 'blue', 'fillOpacity': 0.1}
                ).add_to(updated_map)

                # Render the updated Folium map to HTML
                updated_map_html = updated_map.repr_html()

                # Display the updated map in Streamlit
                st.components.v1.html(updated_map_html, width=700, height=500)

if _name_ == "_main_":
    main()