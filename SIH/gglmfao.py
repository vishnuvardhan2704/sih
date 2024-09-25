import streamlit as st
import folium
import ee
from streamlit.components.v1 import html

# Initialize Earth Engine
ee.Authenticate()
ee.Initialize(project='ee-dartsih')

# Add custom CSS for aesthetics
def add_custom_css():
    st.markdown("""
        <style>
        body {
            background-color: #0B0C10;
            color: #66FCF1;
        }
        .stButton button {
            background-color: #1F2833;
            color: #66FCF1;
            border-radius: 8px;
        }
        .stTextInput input, .stNumberInput input, .stDateInput input {
            background-color: #1F2833;
            color: white;
            border-radius: 8px;
            border: 2px solid #66FCF1;
        }
        .stForm button {
            background-color: #45A29E;
            color: white;
            border-radius: 8px;
        }
        .stTitle h1 {
            color: #66FCF1;
        }
        </style>
    """, unsafe_allow_html=True)

add_custom_css()

def get_buffered_aoi(center_lon, center_lat, radius_km):
    point = ee.Geometry.Point([center_lon, center_lat])
    buffer = point.buffer(radius_km * 1000)  # Convert km to meters
    return buffer

def enhanced_lee_filter(image):
    weights = ee.Kernel.square(radius=1)
    mean = image.reduceNeighborhood(ee.Reducer.mean(), weights)
    variance = image.reduceNeighborhood(ee.Reducer.variance(), weights)
    b = variance.divide(variance.add(1e-6))  # Avoid division by zero
    result = mean.add(b.multiply(image.subtract(mean)))
    return result

def boxcar_filter(image):
    kernel = ee.Kernel.square(radius=1)
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

def process_images(aoi, start1, end1, start2, end2):
    try:
        image1 = load_image_collection(aoi, start1, end1)
        image2 = load_image_collection(aoi, start2, end2)
        image1_filtered = enhanced_lee_filter(image1)
        image2_filtered = enhanced_lee_filter(image2)
        image1_boxcar = boxcar_filter(image1_filtered)
        image2_boxcar = boxcar_filter(image2_filtered)

        mask = ee.Image.constant(1).clip(aoi)
        image1_boxcar = image1_boxcar.updateMask(mask)
        image2_boxcar = image2_boxcar.updateMask(mask)
        diff = image2_boxcar.subtract(image1_boxcar).abs()

        threshold = 0.1
        changes = diff.gt(threshold)

        return image1_boxcar, image2_boxcar, diff, changes
    
    except Exception as e:
        st.error(f"Error processing images: {e}")
        return None, None, None, None

def main():
    st.title("Space Tech SAR Change Detection")

    # Placeholder for coordinates
    if "selected_coordinates" not in st.session_state:
        st.session_state["selected_coordinates"] = None

    folium_map = folium.Map(location=[20, 77], zoom_start=5)
    folium.LatLngPopup().add_to(folium_map)
    folium.LayerControl().add_to(folium_map)

    map_html = folium_map._repr_html_()
    st.write("Select a point on the map and specify a buffer radius:")
    st.components.v1.html(map_html, width=700, height=500)

    with st.form("input_form"):
        radius_km = st.number_input("Buffer Radius (km):", value=10)
        lat_lon = st.text_input("Selected Coordinates (lat, lon):", key="selected_coordinates")
        start1 = st.date_input("Image 1 Start Date")
        end1 = st.date_input("Image 1 End Date")
        start2 = st.date_input("Image 2 Start Date")
        end2 = st.date_input("Image 2 End Date")
        submitted = st.form_submit_button("Apply")

        if submitted:
            if lat_lon:
                center_lat, center_lon = map(float, lat_lon.split(","))
                aoi = get_buffered_aoi(center_lon, center_lat, radius_km)
                image1_boxcar, image2_boxcar, diff, changes = process_images(aoi, str(start1), str(end1), str(start2), str(end2))

                if image1_boxcar and image2_boxcar and diff:
                    vis_params = {'min': -25, 'max': 0}
                    diff_vis_params = {'min': 0, 'max': 10}
                    map_id_image1 = ee.Image(image1_boxcar).getMapId(vis_params)
                    map_id_image2 = ee.Image(image2_boxcar).getMapId(vis_params)
                    map_id_diff = ee.Image(diff).getMapId(diff_vis_params)

                    updated_map = folium.Map(location=[center_lat, center_lon], zoom_start=10)
                    folium.TileLayer(
                        tiles=map_id_image1['tile_fetcher'].url_format,
                        attr='Map data © Google',
                        overlay=True,
                        name='Image 1 (Filtered & Boxcar)'
                    ).add_to(updated_map)
                    folium.TileLayer(
                        tiles=map_id_image2['tile_fetcher'].url_format,
                        attr='Map data © Google',
                        overlay=True,
                        name='Image 2 (Filtered & Boxcar)'
                    ).add_to(updated_map)
                    folium.TileLayer(
                        tiles=map_id_diff['tile_fetcher'].url_format,
                        attr='Map data © Google',
                        overlay=True,
                        name='Difference Image'
                    ).add_to(updated_map)

                    geojson_buffer = ee.FeatureCollection([ee.Feature(aoi)]).getInfo()
                    folium.GeoJson(
                        data=geojson_buffer,
                        style_function=lambda x: {'color': 'blue', 'fillOpacity': 0.1}
                    ).add_to(updated_map)

                    updated_map_html = updated_map._repr_html_()
                    st.components.v1.html(updated_map_html, width=700, height=500)

if __name__ == "__main__":
    main()
