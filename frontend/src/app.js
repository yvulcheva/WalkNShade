// Initialize the map
const lat = 42.6977; // Latitude for Sofia, Bulgaria
const lng = 23.3219; // Longitude for Sofia, Bulgaria
const zoom = 13; // Initial zoom level

const map = L.map("map").setView([lat, lng], zoom);
let marker,
  circle,
  findCurrentLocation = false,
  walking = false;

let lastShadePathLayer = null;
let lastShortPathLayer = null;
let pointOfIntrestLayers = [];
let cadastreLayer = [];
let walkingPathLayer = [];
let shadesLayer = [];

let selectedPOICoords = null;

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

const userPointStill = L.icon({
  iconUrl: "pictures/user-location.png",
  iconSize: [35, 35], // Size of the icon
  iconAnchor: [15, 15], // Point of the icon which will correspond to marker's location
});

const userPointWalking = L.icon({
  iconUrl: "pictures/walking.png",
  iconSize: [25, 25],
  iconAnchor: [15, 15],
});

const poiIcon = L.icon({
  iconUrl: "pictures/point.png",
  iconSize: [32, 32],
  iconAnchor: [16, 32],
});
const poiIconSelected = L.icon({
  iconUrl: "pictures/point-clicked.png",
  iconSize: [36, 36],
  iconAnchor: [18, 36],
});

navigator.geolocation.watchPosition(updateLocation, onError);

function updateLocation(position) {
  console.log("Updating location with new position:", position);
  const lat = position.coords.latitude;
  const lng = position.coords.longitude;
  const accuracy = position.coords.accuracy;

  if (!marker) {
    marker = L.marker([lat, lng], { icon: userPointStill }).addTo(map);
    circle = L.circle([lat, lng], { radius: accuracy }).addTo(map);
  } else {
    marker.setLatLng([lat, lng]);
    circle.setLatLng([lat, lng]);
    circle.setRadius(accuracy);
  }

  zoomToLocation();
}

function walkingMode(type) {
  marker.setIcon(userPointWalking);

  // Use marker's current position as start
  const startLatLng = marker.getLatLng();
  const start = [startLatLng.lng, startLatLng.lat];
  const end = selectedPOICoords;

  const date = new Date();
  const sunPosition = SunCalc.getPosition(
    date,
    startLatLng.lat,
    startLatLng.lng
  );
  const sunAzimuth = (sunPosition.azimuth * 180) / Math.PI;
  const sunAltitude = (sunPosition.altitude * 180) / Math.PI;
  console.log("Sun position:", sunAzimuth, sunAltitude);

  if (type === "shade") {
    fetchShortestShadePath(start, end, sunAzimuth, sunAltitude);
  } else if (type === "short") {
    fetchShortestPath(start, end);
  } else {
    console.error("Invalid path type:", type);
    return;
  }
}

function stillMode() {
  marker.setIcon(userPointStill);
  if (lastShadePathLayer) {
    map.removeLayer(lastShadePathLayer);
    lastShadePathLayer = null;
  }
  if (lastShortPathLayer) {
    map.removeLayer(lastShortPathLayer);
    lastShortPathLayer = null;
  }

  console.log("Walking mode disabled, path cleared.");
}

function onError(error) {
  if (error.code === 1) {
    alert(
      "Location access denied. Please allow location access in your browser settings."
    );
  } else {
    console.warn(`Initial geolocation error (${error.code}): ${error.message}`);
  }
  // Fallback: show a marker at the map center if marker is not set
  if (!marker) {
    marker = L.marker([lat, lng], { icon: userPointStill }).addTo(map);
    circle = L.circle([lat, lng], { radius: 100 }).addTo(map);
    zoomToLocation();
    console.log("Fallback marker set at map center.");
  }
}

function zoomToLocation() {
  console.log("Zoom in current location");
  if (marker && circle && !findCurrentLocation) {
    findCurrentLocation = map.fitBounds(circle.getBounds());
  }
}

function currentLocation() {
  console.log("Current location button clicked");
  findCurrentLocation = false;
  zoomToLocation();
}

function findRoute(type) {
  console.log("Start direction button clicked");
  if (!selectedPOICoords) {
    alert("Please select a point of interest on the map.");
    return;
  }

  if (marker) {
    walkingMode(type);
    findCurrentLocation = false;
    zoomToLocation();
  } else {
    alert("Please wait for the location to be determined.");
    return;
  }
}

function findShadeRoute() {
  findRoute("shade");
}

function findShortRoute() {
  findRoute("short");
}

function resetRoute() {
  console.log("Reset route button clicked");
  stillMode();
}

const fetchCadastreData = async () => {
  try {
    // Remove previous cadastre layers
    cadastreLayer.forEach((layer) => map.removeLayer(layer));
    cadastreLayer = [];

    const response = await fetch("http://127.0.0.1:8686/api/cadastre");
    const geojsonData = await response.json();
    console.log("GeoJSON data fetched:");

    // Loop through each feature and add to the map
    geojsonData.forEach((item) => {
      const layer = L.geoJSON(item.geojson).addTo(map);
      cadastreLayer.push(layer);
    });
    console.log("GeoJSON data added to the map.");
  } catch (error) {
    console.error("Error fetching GeoJSON data:", error);
  }
};

const fetchWalkingData = async () => {
  try {
    // Remove previous walking path layers
    walkingPathLayer.forEach((layer) => map.removeLayer(layer));
    walkingPathLayer = [];

    const response = await fetch("http://127.0.1:8686/api/walkpath");
    const geojsonData = await response.json();
    console.log("Walking path GeoJSON data fetched");

    geojsonData.forEach((item) => {
      const layer = L.geoJSON(item.geojson).addTo(map);
      walkingPathLayer.push(layer);
      layer.bringToBack();
    });

    console.log("Walking path GeoJSON data added to the map.");
  } catch (error) {
    console.error("Error fetching walking path GeoJSON data:", error);
  }
};

const fetchShadowsData = async () => {
  try {
    const date = new Date();
    const sunPosition = SunCalc.getPosition(date, lat, lng);

    const sunAzimuth = (sunPosition.azimuth * 180) / Math.PI;
    const sunAltitude = (sunPosition.altitude * 180) / Math.PI;

    // Remove previous shadows path layers
    shadesLayer.forEach((layer) => map.removeLayer(layer));
    shadesLayer = [];
    const response = await fetch("http://127.0.0.1:8686/api/shade", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        sun_azimuth: sunAzimuth,
        sun_altitude: sunAltitude,
      }),
    });

    const geojsonData = await response.json();
    console.log("Shade polygons GeoJSON data fetched");

    geojsonData.forEach((item) => {
      const geo = item.geojson ? item.geojson : item;
      const layer = L.geoJSON(geo).addTo(map);
      shadesLayer.push(layer);
    });

    console.log("Shade polygons GeoJSON data added to the map.");
  } catch (error) {
    console.error("Error fetching shade polygons GeoJSON data:", error);
  }
};

const fetchHeltCentersData = async (type) => {
  try {
    // Remove previous health center layers
    pointOfIntrestLayers.forEach((layer) => map.removeLayer(layer));
    pointOfIntrestLayers = [];

    stillMode(); // Reset walking mode if it was active
    const response = await fetch("http://127.0.0.1:8686/api/health-centers", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        type: type, // e.g. "hospital", "clinic", etc.
      }),
    });

    const geojsonData = await response.json();
    console.log("Health centers GeoJSON data fetched");

    // Loop through each feature and add to the map
    geojsonData.forEach((item) => {
      const layer = L.geoJSON(item.geojson, {
        pointToLayer: function (feature, latlng) {
          return L.marker(latlng, { icon: poiIcon });
        },
      }).addTo(map);

      pointOfIntrestLayers.push(layer);
      layer.eachLayer(function (featureLayer) {
        featureLayer.on("click", function (e) {
          const latlng = featureLayer.getLatLng();
          const coords = [latlng.lng, latlng.lat];
          const isSelected =
            selectedPOICoords &&
            selectedPOICoords[0] === coords[0] &&
            selectedPOICoords[1] === coords[1];

          if (isSelected) {
            if (featureLayer.setIcon) featureLayer.setIcon(poiIcon);
            selectedPOICoords = null;
            return;
          }

          pointOfIntrestLayers.forEach((layer) => {
            if (layer.eachLayer) {
              layer.eachLayer((fl) => fl.setIcon && fl.setIcon(poiIcon));
            }
          });

          if (featureLayer.setIcon) featureLayer.setIcon(poiIconSelected);
          if (
            featureLayer.feature &&
            featureLayer.feature.geometry &&
            featureLayer.feature.geometry.type === "Point"
          ) {
            selectedPOICoords = featureLayer.feature.geometry.coordinates;
          } else if (featureLayer.getLatLng) {
            selectedPOICoords = coords;
          }
        });

        if (item.name) {
          featureLayer.bindTooltip(item.name, {
            permanent: false,
            direction: "top",
          });
        }
      });
    });
    console.log("Health centers GeoJSON data added to the map.");
  } catch (error) {
    console.error("Error fetching health centers GeoJSON data:", error);
  }
};

const fetchShortestShadePath = async (start, end, sunAzimuth, sunAltitude) => {
  try {
    const response = await fetch(
      "http://127.0.0.1:8686/api/shortest-shaded-path",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          start: start,
          end: end,
          sun_azimuth: sunAzimuth,
          sun_altitude: sunAltitude,
        }),
      }
    );

    const data = await response.json();
    console.log("Shortest path result:", data);

    if (lastShadePathLayer) {
      map.removeLayer(lastShadePathLayer);
      lastShadePathLayer = null;
    }

    if (data && data.geometry) {
      lastShadePathLayer = L.geoJSON(data, {
        style: {
          color: "#00FF00",
          weight: 5,
        },
      }).addTo(map);

      lastShadePathLayer.bringToFront();
    }
  } catch (error) {
    console.error("Error fetching shaded path:", error);
  }
};

const fetchShortestPath = async (start, end) => {
  try {
    const response = await fetch("http://127.0.0.1:8686/api/shortest-path", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        start: start,
        end: end,
      }),
    });

    const data = await response.json();
    console.log("Shortest path result:", data);
    // Remove previous path layer if exists
    if (lastShortPathLayer) {
      map.removeLayer(lastShortPathLayer);
      lastShortPathLayer = null;
    }

    if (data && data.geometry) {
      lastShortPathLayer = L.geoJSON(data, {
        style: {
          color: "#FFFF00",
          weight: 5,
        },
      }).addTo(map);

      lastShortPathLayer.bringToFront();
    }
  } catch (error) {
    console.error("Error fetching shaded path:", error);
  }
};

function onPointOfInterestTypeChange() {
  const select = document.getElementById("pointOfIntrestType");
  const type = select.value;
  selectedPOICoords = null;

  if (type === "none") {
    console.log("Remove previous layers");
    pointOfIntrestLayers.forEach((layer) => map.removeLayer(layer));
    pointOfIntrestLayers = [];
  } else {
    console.log("Fetch new health centers data for type:", type);
    fetchHeltCentersData(type);
  }
}

function onGisLayerChange() {
  const select = document.getElementById("gisLayer");
  const layer = select.value;

  if (layer === "cadastre") {
    console.log("Fetching cadastre data");
    fetchCadastreData();
  } else if (layer === "walkpath") {
    console.log("Fetching walking path data");
    fetchWalkingData();
  } else if (layer === "shades") {
    console.log("Fetching shades data");
    fetchShadowsData();
  } else {
    console.log("No GIS layer selected");

    cadastreLayer.forEach((layer) => map.removeLayer(layer));
    cadastreLayer = [];
    walkingPathLayer.forEach((layer) => map.removeLayer(layer));
    walkingPathLayer = [];
    shadesLayer.forEach((layer) => map.removeLayer(layer));
    shadesLayer = [];
  }
}
