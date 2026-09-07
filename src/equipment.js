import * as THREE from 'three';

export const EQUIPMENT_TYPES = [
  { id: 'pump', label: 'Pump', icon: '🔧', color: 0x4f8cff },
  { id: 'motor', label: 'Motor', icon: '⚙️', color: 0xffa64f },
  { id: 'valve', label: 'Valve', icon: '🔩', color: 0x5fd97a },
  { id: 'tank', label: 'Tank', icon: '🛢️', color: 0x9a7bd1 },
  { id: 'conveyor', label: 'Conveyor', icon: '➡️', color: 0xd1a05f },
  { id: 'sensor', label: 'Sensor', icon: '📡', color: 0xff5f9d },
  { id: 'fan', label: 'Fan', icon: '💨', color: 0x5fc7d1 },
  { id: 'compressor', label: 'Compressor', icon: '🗜️', color: 0xd15f5f },
  { id: 'generator', label: 'Generator', icon: '🔌', color: 0xd1c95f },
  { id: 'panel', label: 'Control Panel', icon: '🖥️', color: 0x8a8f99 },
];

function roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function makeLabelSprite(text) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const fontSize = 44;
  ctx.font = `600 ${fontSize}px Segoe UI, sans-serif`;
  const padding = 16;
  const textWidth = Math.max(ctx.measureText(text).width, 10);
  canvas.width = textWidth + padding * 2;
  canvas.height = fontSize + padding * 2;

  // Re-apply font after resizing the canvas (resizing clears context state).
  ctx.font = `600 ${fontSize}px Segoe UI, sans-serif`;
  ctx.fillStyle = 'rgba(20, 22, 26, 0.88)';
  roundRectPath(ctx, 0, 0, canvas.width, canvas.height, 14);
  ctx.fill();
  ctx.fillStyle = '#ffffff';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, padding, canvas.height / 2 + 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  const material = new THREE.SpriteMaterial({
    map: texture,
    depthTest: false,
    depthWrite: false,
    sizeAttenuation: true,
  });
  const sprite = new THREE.Sprite(material);
  const scaleFactor = 0.011;
  sprite.scale.set(canvas.width * scaleFactor, canvas.height * scaleFactor, 1);
  sprite.userData.isLabel = true;
  sprite.renderOrder = 999;
  return sprite;
}

function buildShape(typeId, color) {
  const material = new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.25 });
  const group = new THREE.Group();

  switch (typeId) {
    case 'pump': {
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.35, 0.5, 16), material);
      body.position.y = 0.25;
      const inlet = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.4, 12), material);
      inlet.rotation.z = Math.PI / 2;
      inlet.position.set(0.35, 0.25, 0);
      group.add(body, inlet);
      break;
    }
    case 'motor': {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.4, 0.4), material);
      body.position.y = 0.2;
      const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.3, 12), material);
      shaft.rotation.z = Math.PI / 2;
      shaft.position.set(0.4, 0.2, 0);
      group.add(body, shaft);
      break;
    }
    case 'valve': {
      const body = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 16), material);
      body.position.y = 0.2;
      const handle = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.05, 0.05), material);
      handle.position.y = 0.42;
      group.add(body, handle);
      break;
    }
    case 'tank': {
      const body = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1, 20), material);
      body.position.y = 0.5;
      group.add(body);
      break;
    }
    case 'conveyor': {
      const body = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.15, 0.5), material);
      body.position.y = 0.4;
      const leg1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.4, 0.4), material);
      leg1.position.set(-0.6, 0.2, 0);
      const leg2 = leg1.clone();
      leg2.position.x = 0.6;
      group.add(body, leg1, leg2);
      break;
    }
    case 'sensor': {
      const body = new THREE.Mesh(new THREE.ConeGeometry(0.15, 0.3, 12), material);
      body.position.y = 0.15;
      group.add(body);
      break;
    }
    case 'fan': {
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.3, 12), material);
      hub.rotation.x = Math.PI / 2;
      hub.position.y = 0.4;
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.35, 0.03, 8, 24), material);
      ring.position.y = 0.4;
      group.add(hub, ring);
      break;
    }
    case 'compressor': {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.5, 0.5), material);
      body.position.y = 0.25;
      const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.6, 16), material);
      tank.rotation.z = Math.PI / 2;
      tank.position.set(0, 0.1, 0.4);
      group.add(body, tank);
      break;
    }
    case 'generator': {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.45, 0.45), material);
      body.position.y = 0.225;
      group.add(body);
      break;
    }
    case 'panel': {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.7, 0.1), material);
      body.position.y = 0.35;
      group.add(body);
      break;
    }
    default: {
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.4, 0.4), material);
      body.position.y = 0.2;
      group.add(body);
    }
  }

  return group;
}

/** Builds a placeholder 3D object (shape + name label) for the given equipment type. */
export function createEquipmentObject(typeId, name) {
  const type = EQUIPMENT_TYPES.find((t) => t.id === typeId) || EQUIPMENT_TYPES[0];
  const group = buildShape(type.id, type.color);
  group.userData.equipmentType = type.id;

  const label = makeLabelSprite(name || type.label);
  positionLabel(group, label);
  group.add(label);

  return group;
}

export function positionLabel(group, label) {
  const bbox = new THREE.Box3().setFromObject(group);
  const height = Number.isFinite(bbox.max.y - bbox.min.y) ? bbox.max.y - bbox.min.y : 0.5;
  const gap = 0.18;
  // Sprites anchor at their center, so clear the shape's top by half the label's own height too.
  label.position.set(0, height + label.scale.y / 2 + gap, 0);
}

/** Replaces an equipment object's floating name label after a rename. */
export function updateEquipmentLabel(group, name) {
  const oldLabel = group.children.find((c) => c.userData.isLabel);
  if (oldLabel) {
    group.remove(oldLabel);
    oldLabel.material.map?.dispose();
    oldLabel.material.dispose();
  }
  const label = makeLabelSprite(name);
  positionLabel(group, label);
  group.add(label);
}

export function disposeEquipmentObject(group) {
  group.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) {
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      mats.forEach((m) => {
        m.map?.dispose();
        m.dispose();
      });
    }
  });
}
