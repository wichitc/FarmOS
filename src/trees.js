import * as THREE from 'three';
import { makeLabelSprite, positionLabel } from './equipment.js';

// Tree type ids are prefixed with "tree_" so the backend dashboard (and any
// equipment-only listing) can cheaply tell them apart from real machinery.
export const TREE_TYPES = [
  { id: 'tree_mango', label: 'Mango', icon: '🥭', canopy: 0x4c9a4a, fruit: 0xf2a33c, shape: 'round' },
  { id: 'tree_durian', label: 'Durian', icon: '🌰', canopy: 0x3f7a3f, fruit: 0x7a5a2a, shape: 'round' },
  { id: 'tree_longan', label: 'Longan', icon: '🟤', canopy: 0x4c9a4a, fruit: 0x8a6a3a, shape: 'round' },
  { id: 'tree_rambutan', label: 'Rambutan', icon: '🔴', canopy: 0x4c9a4a, fruit: 0xd1495f, shape: 'round' },
  { id: 'tree_mangosteen', label: 'Mangosteen', icon: '🟣', canopy: 0x3f7a3f, fruit: 0x6a3a7a, shape: 'round' },
  { id: 'tree_lime', label: 'Lime', icon: '🍋', canopy: 0x4c9a4a, fruit: 0x8fd14f, shape: 'round' },
  { id: 'tree_pomelo', label: 'Pomelo', icon: '🍈', canopy: 0x4c9a4a, fruit: 0xd8dd8a, shape: 'round' },
  { id: 'tree_papaya', label: 'Papaya', icon: '🟠', canopy: 0x4a8a5a, fruit: 0xe08a3c, shape: 'round' },
  { id: 'tree_banana', label: 'Banana', icon: '🍌', canopy: 0x5aa04a, fruit: 0xe8c93c, shape: 'banana' },
  { id: 'tree_coconut', label: 'Coconut', icon: '🥥', canopy: 0x3f7a3f, fruit: 0x7a5a3a, shape: 'palm' },
];

function buildTrunk(radiusBottom, height, color = 0x6b4a2f) {
  const trunk = new THREE.Mesh(
    new THREE.CylinderGeometry(radiusBottom * 0.75, radiusBottom, height, 8),
    new THREE.MeshStandardMaterial({ color, roughness: 0.9 })
  );
  trunk.position.y = height / 2;
  return trunk;
}

const ROUND_FRUIT_OFFSETS = [
  [0.28, 0.05, 0.2],
  [-0.25, -0.1, 0.22],
  [0.1, -0.15, -0.28],
  [-0.2, 0.15, -0.18],
];

function buildRoundCanopy(canopyColor, fruitColor, canopyY, canopyRadius) {
  const group = new THREE.Group();
  const canopyMat = new THREE.MeshStandardMaterial({ color: canopyColor, roughness: 0.85, flatShading: true });
  const canopy = new THREE.Mesh(new THREE.IcosahedronGeometry(canopyRadius, 1), canopyMat);
  canopy.position.y = canopyY;
  group.add(canopy);

  const fruitMat = new THREE.MeshStandardMaterial({ color: fruitColor, roughness: 0.5 });
  const scale = canopyRadius / 0.5;
  for (const [ox, oy, oz] of ROUND_FRUIT_OFFSETS) {
    const fruit = new THREE.Mesh(new THREE.SphereGeometry(canopyRadius * 0.18, 8, 8), fruitMat);
    fruit.position.set(ox * scale, canopyY + oy * scale, oz * scale);
    group.add(fruit);
  }
  return group;
}

function buildBananaTree(canopyColor, fruitColor) {
  const group = new THREE.Group();
  group.add(buildTrunk(0.14, 1.1, 0x6a9a4a));

  const leafMat = new THREE.MeshStandardMaterial({ color: canopyColor, roughness: 0.8, side: THREE.DoubleSide });
  const leafCount = 6;
  for (let i = 0; i < leafCount; i++) {
    const leaf = new THREE.Mesh(new THREE.PlaneGeometry(0.9, 0.28), leafMat);
    leaf.position.set(0, 1.15, 0);
    leaf.rotation.y = (i / leafCount) * Math.PI * 2;
    leaf.rotation.z = THREE.MathUtils.degToRad(20);
    leaf.translateX(0.45);
    group.add(leaf);
  }

  const fruitMat = new THREE.MeshStandardMaterial({ color: fruitColor, roughness: 0.6 });
  for (let i = 0; i < 4; i++) {
    const banana = new THREE.Mesh(new THREE.SphereGeometry(0.06, 8, 8), fruitMat);
    banana.scale.set(1, 2.2, 1);
    banana.position.set(0.09 * (i - 1.5), 0.85, 0.15);
    banana.rotation.z = THREE.MathUtils.degToRad(70);
    group.add(banana);
  }
  return group;
}

function buildPalmTree(canopyColor, fruitColor) {
  const group = new THREE.Group();
  group.add(buildTrunk(0.09, 1.6, 0x8a6a4a));

  const frondMat = new THREE.MeshStandardMaterial({ color: canopyColor, roughness: 0.8, side: THREE.DoubleSide });
  const frondCount = 6;
  for (let i = 0; i < frondCount; i++) {
    const frond = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.9, 4), frondMat);
    frond.position.set(0, 1.6, 0);
    frond.rotation.y = (i / frondCount) * Math.PI * 2;
    frond.rotation.z = THREE.MathUtils.degToRad(70);
    frond.translateY(0.45);
    group.add(frond);
  }

  const fruitMat = new THREE.MeshStandardMaterial({ color: fruitColor, roughness: 0.6 });
  for (let i = 0; i < 3; i++) {
    const angle = (i / 3) * Math.PI * 2;
    const nut = new THREE.Mesh(new THREE.SphereGeometry(0.09, 8, 8), fruitMat);
    nut.position.set(Math.cos(angle) * 0.12, 1.55, Math.sin(angle) * 0.12);
    group.add(nut);
  }
  return group;
}

function buildTreeShape(type) {
  if (type.shape === 'banana') return buildBananaTree(type.canopy, type.fruit);
  if (type.shape === 'palm') return buildPalmTree(type.canopy, type.fruit);

  const group = new THREE.Group();
  group.add(buildTrunk(0.13, 0.7, 0x6b4a2f));
  group.add(buildRoundCanopy(type.canopy, type.fruit, 1.0, 0.5));
  return group;
}

/** Builds a placeholder 3D object (canopy + trunk + name label) for the given fruit tree type. */
export function createTreeObject(typeId, name) {
  const type = TREE_TYPES.find((t) => t.id === typeId) || TREE_TYPES[0];
  const group = buildTreeShape(type);
  group.userData.treeType = type.id;

  const label = makeLabelSprite(name || type.label);
  positionLabel(group, label);
  group.add(label);

  return group;
}

/** Replaces a tree object's floating name label after a rename. */
export function updateTreeLabel(group, name) {
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
