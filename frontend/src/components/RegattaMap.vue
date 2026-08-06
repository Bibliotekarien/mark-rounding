<script setup>
// MapLibre map with one marker per regatta (OSM + OpenSeaMap raster tiles,
// same sources as gribranker's AreaMap).
import maplibregl from "maplibre-gl";
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useRouter } from "vue-router";

const props = defineProps({
  regattas: { type: Array, default: () => [] },
});

const container = ref(null);
const router = useRouter();
let map = null;
let markers = [];

const STYLE = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap-bidragsgivare",
    },
    seamark: {
      type: "raster",
      tiles: ["https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenSeaMap",
    },
  },
  layers: [
    { id: "osm", type: "raster", source: "osm" },
    { id: "seamark", type: "raster", source: "seamark" },
  ],
};

function render() {
  if (!map) return;
  markers.forEach((m) => m.remove());
  markers = [];
  const withCoords = props.regattas.filter((r) => r.lat != null && r.lon != null);
  if (!withCoords.length) return;

  const bounds = new maplibregl.LngLatBounds();
  for (const regatta of withCoords) {
    const popup = new maplibregl.Popup({ offset: 18 }).setHTML(
      `<strong>${regatta.name}</strong><br>${regatta.venue || ""}`
    );
    const marker = new maplibregl.Marker({ color: "#0ea5e9" })
      .setLngLat([regatta.lon, regatta.lat])
      .setPopup(popup)
      .addTo(map);
    marker.getElement().style.cursor = "pointer";
    marker.getElement().addEventListener("click", (event) => {
      event.stopPropagation();
      router.push(`/regatta/${regatta.slug}`);
    });
    markers.push(marker);
    bounds.extend([regatta.lon, regatta.lat]);
  }
  if (withCoords.length === 1) {
    map.setCenter(bounds.getCenter());
    map.setZoom(9);
  } else {
    map.fitBounds(bounds, { padding: 60, maxZoom: 10 });
  }
}

onMounted(() => {
  map = new maplibregl.Map({
    container: container.value,
    style: STYLE,
    center: [17.0, 59.4],
    zoom: 5,
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
  map.on("load", render);
});

watch(() => props.regattas, render, { deep: true });

onBeforeUnmount(() => {
  if (map) map.remove();
});
</script>

<template>
  <div ref="container" class="map"></div>
</template>
