import {
  CircleUserRound,
  GalleryVerticalEnd,
  Image,
  Instagram,
  Monitor,
  MonitorUp,
  RectangleHorizontal,
  Smartphone,
  SmartphoneCharging,
  Tablet,
} from "lucide-react";

// formats.json içindeki "icon" alanı -> lucide bileşeni.
// Yeni preset'e yeni ikon gerekiyorsa buraya bir satır ekleyin;
// eşleşme yoksa genel resim ikonu kullanılır.
const PRESET_ICONS = {
  monitor: Monitor,
  "monitor-up": MonitorUp,
  "rectangle-horizontal": RectangleHorizontal,
  smartphone: Smartphone,
  "smartphone-charging": SmartphoneCharging,
  tablet: Tablet,
  instagram: Instagram,
  "gallery-vertical-end": GalleryVerticalEnd,
  "circle-user-round": CircleUserRound,
};

export function iconFor(name) {
  return PRESET_ICONS[name] || Image;
}
