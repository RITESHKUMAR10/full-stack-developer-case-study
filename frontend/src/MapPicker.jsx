import { useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Rectangle, useMap, useMapEvents } from "react-leaflet";
import { useEffect } from "react";

function Clicks({ mode, onPoint, onBox }) {
  const [first, setFirst] = useState(null);
  useMapEvents({
    click(e) {
      const { lat, lng } = e.latlng;
      if (mode === "point") return onPoint(lat, lng);
      if (!first) return setFirst({ lat, lng });
      onBox({
        south: Math.min(first.lat, lat), north: Math.max(first.lat, lat),
        west: Math.min(first.lng, lng), east: Math.max(first.lng, lng),
      });
      setFirst(null);
    },
  });
  return first ? <CircleMarker center={[first.lat, first.lng]} radius={5} /> : null;
}

function Recenter({ lat, lon }) {
  const map = useMap();
  useEffect(() => { map.setView([lat, lon], map.getZoom()); }, [lat, lon]); // eslint-disable-line
  return null;
}

export default function MapPicker({ region, mode, onPoint, onBox }) {
  return (
    <MapContainer center={[region.lat, region.lon]} zoom={5} className="map" worldCopyJump>
      <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <Clicks mode={mode} onPoint={onPoint} onBox={onBox} />
      <Recenter lat={region.lat} lon={region.lon} />
      <CircleMarker center={[region.lat, region.lon]} radius={7} pathOptions={{ color: "#c2410c", fillOpacity: 0.8 }} />
      {region.box && (
        <Rectangle bounds={[[region.box.south, region.box.west], [region.box.north, region.box.east]]}
                   pathOptions={{ color: "#c2410c" }} />
      )}
    </MapContainer>
  );
}
