import * as THREE from 'three';
import { IfcViewerAPI } from 'web-ifc-viewer';
import {
  EQUIPMENT_TYPES,
  createEquipmentObject,
  updateEquipmentLabel,
  disposeEquipmentObject,
} from './equipment.js';
import { TREE_TYPES, createTreeObject, updateTreeLabel } from './trees.js';
import {
  checkBackendStatus,
  uploadModel,
  listModels,
  deleteModelOnServer,
  modelFileUrl,
  listEquipmentOnServer,
  createEquipmentOnServer,
  updateEquipmentOnServer,
  deleteEquipmentOnServer,
  getEquipmentHealth,
  getDashboardSummary,
} from './api.js';
import './style.css';

const EQ_MIME = 'application/x-ifcviewer-equipment';

const container = document.getElementById('viewer-container');
const dropOverlay = document.getElementById('drop-overlay');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');
const fileInput = document.getElementById('file-input');
const btnOpen = document.getElementById('btn-open');
const btnOpen2 = document.getElementById('btn-open-2');
const btnFit = document.getElementById('btn-fit');
const btnTree = document.getElementById('btn-tree');
const btnProps = document.getElementById('btn-props');
const treePanel = document.getElementById('tree-panel');
const propsPanel = document.getElementById('props-panel');
const spatialTreeBody = document.getElementById('spatial-tree-body');
const propsContent = document.getElementById('props-content');
const modelNameEl = document.getElementById('model-name');
const equipmentLibraryEl = document.getElementById('equipment-library');
const eqPlaceHintEl = document.getElementById('eq-place-hint');
const eqPlaceHintTextEl = document.getElementById('eq-place-hint-text');
const btnCancelPlace = document.getElementById('btn-cancel-place');
const equipmentInstancesEl = document.getElementById('equipment-instances');
const btnExportLayout = document.getElementById('btn-export-layout');
const btnImportLayout = document.getElementById('btn-import-layout');
const layoutFileInput = document.getElementById('layout-file-input');
const treeLibraryEl = document.getElementById('tree-library');
const treeInstancesEl = document.getElementById('tree-instances');
const btnExportLayoutTrees = document.getElementById('btn-export-layout-trees');
const btnImportLayoutTrees = document.getElementById('btn-import-layout-trees');
const serverModelsListEl = document.getElementById('server-models-list');
const btnRefreshModels = document.getElementById('btn-refresh-models');
const btnSaveModelServer = document.getElementById('btn-save-model-server');
const btnModeView = document.getElementById('btn-mode-view');
const btnModeEdit = document.getElementById('btn-mode-edit');
const tabBtnEquipment = document.getElementById('tab-btn-equipment');
const tabBtnTrees = document.getElementById('tab-btn-trees');
const btnDashboard = document.getElementById('btn-dashboard');
const btnCloseDashboard = document.getElementById('btn-close-dashboard');
const dashboardOverlay = document.getElementById('dashboard-overlay');
const dashboardBody = document.getElementById('dashboard-body');

const viewer = new IfcViewerAPI({ container });
viewer.axes.setAxes();
viewer.grid.setGrid();
viewer.IFC.setWasmPath('/wasm/');

const equipmentGroup = new THREE.Group();
equipmentGroup.name = 'DigitalTwinEquipment';
viewer.context.getScene().add(equipmentGroup);

let currentModelID = null;
let currentModelName = null;
let currentServerModelId = null;
let currentLocalFile = null;
let backendAvailable = false;
let selectedRow = null;

/** @type {Map<string, THREE.Object3D>} */
const equipmentObjects = new Map();
/** @type {Array<object>} */
let placedEquipment = [];
let selectedEquipmentId = null;
let selectionBoxHelper = null;
let armedEquipmentType = null;
let isEditable = true;

function uuid() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// ---------- Tabs ----------
document.querySelectorAll('.tab-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(`${btn.dataset.tab}-content`).classList.add('active');
  });
});

// ---------- View Only / Editable mode ----------
function setMode(editable) {
  isEditable = editable;
  btnModeView.classList.toggle('active', !editable);
  btnModeEdit.classList.toggle('active', editable);
  tabBtnEquipment.hidden = !editable;
  tabBtnTrees.hidden = !editable;

  if (!editable) {
    disarmPlacement();
    if (tabBtnEquipment.classList.contains('active') || tabBtnTrees.classList.contains('active')) {
      document.querySelector('.tab-btn[data-tab="tree"]').click();
    }
  }

  if (selectedEquipmentId) {
    const obj = equipmentObjects.get(selectedEquipmentId);
    const record = placedEquipment.find((r) => r.id === selectedEquipmentId);
    if (obj && record) showEquipmentProperties(record, obj);
  }
}

btnModeView.addEventListener('click', () => setMode(false));
btnModeEdit.addEventListener('click', () => setMode(true));

// ---------- Panel toggles ----------
btnTree.addEventListener('click', () => {
  treePanel.classList.toggle('collapsed');
  btnTree.classList.toggle('active');
});
btnProps.addEventListener('click', () => {
  propsPanel.classList.toggle('collapsed');
  btnProps.classList.toggle('active');
});
btnFit.addEventListener('click', () => viewer.context.fitToFrame());

// ---------- File opening (IFC models, local) ----------
btnOpen.addEventListener('click', () => fileInput.click());
btnOpen2.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (file) loadFile(file);
  fileInput.value = '';
});

['dragenter', 'dragover'].forEach((evt) => {
  container.addEventListener(evt, (e) => {
    const types = Array.from(e.dataTransfer?.types || []);
    if (types.includes('Files')) {
      e.preventDefault();
      e.stopPropagation();
      dropOverlay.querySelector('.drop-box').classList.add('drag-active');
    } else if (types.includes(EQ_MIME)) {
      e.preventDefault();
      e.stopPropagation();
      container.classList.add('eq-drop-active');
    }
  });
});

['dragleave', 'drop'].forEach((evt) => {
  container.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropOverlay.querySelector('.drop-box').classList.remove('drag-active');
    container.classList.remove('eq-drop-active');
  });
});

container.addEventListener('drop', (e) => {
  const file = e.dataTransfer.files[0];
  if (file && file.name.toLowerCase().endsWith('.ifc')) {
    loadFile(file);
    return;
  }
  const typeId = e.dataTransfer.getData(EQ_MIME);
  if (typeId && isEditable) {
    placeEquipmentFromDrop(e, typeId);
  }
});

async function loadFile(file) {
  dropOverlay.classList.add('hidden');
  loadingOverlay.classList.remove('hidden');
  loadingText.textContent = 'Loading model…';
  clearProperties();
  spatialTreeBody.innerHTML = '<p class="empty-hint">Loading…</p>';

  try {
    const url = URL.createObjectURL(file);
    const model = await viewer.IFC.loadIfcUrl(
      url,
      true,
      (evt) => {
        if (evt.lengthComputable) {
          const pct = Math.round((evt.loaded / evt.total) * 100);
          loadingText.textContent = `Loading model… ${pct}%`;
        }
      },
      (error) => {
        console.error(error);
        loadingText.textContent = 'Failed to load model.';
      }
    );
    URL.revokeObjectURL(url);

    currentModelID = model.modelID;
    currentModelName = file.name;
    currentServerModelId = null;
    currentLocalFile = file;
    modelNameEl.textContent = file.name;
    btnSaveModelServer.hidden = !backendAvailable;
    await buildTree(currentModelID);
    await loadEquipmentForScope();
    refreshServerModelsUI();
  } catch (err) {
    console.error(err);
    alert('Could not load this IFC file. Check the console for details.');
    dropOverlay.classList.remove('hidden');
  } finally {
    loadingOverlay.classList.add('hidden');
  }
}

async function loadModelFromServer(modelId, name) {
  dropOverlay.classList.add('hidden');
  loadingOverlay.classList.remove('hidden');
  loadingText.textContent = `Loading ${name}…`;
  clearProperties();
  spatialTreeBody.innerHTML = '<p class="empty-hint">Loading…</p>';

  try {
    const model = await viewer.IFC.loadIfcUrl(modelFileUrl(modelId), true);
    currentModelID = model.modelID;
    currentModelName = name;
    currentServerModelId = modelId;
    currentLocalFile = null;
    modelNameEl.textContent = name;
    btnSaveModelServer.hidden = true;
    await buildTree(currentModelID);
    await loadEquipmentForScope();
    refreshServerModelsUI();
  } catch (err) {
    console.error(err);
    alert('Could not load this model from the server.');
  } finally {
    loadingOverlay.classList.add('hidden');
  }
}

// ---------- Selection in the 3D view ----------
let dragState = null;
let suppressNextClick = false;

container.addEventListener('mousemove', () => {
  if (dragState) return;
  viewer.IFC.selector.prePickIfcItem();
});

container.addEventListener('mousedown', (e) => {
  if (!isEditable || armedEquipmentType || e.button !== 0) return;
  const obj = pickEquipmentAt(e);
  if (!obj) return;
  const record = placedEquipment.find((r) => r.id === obj.userData.equipmentId);
  if (!record) return;

  e.preventDefault();
  suppressNextClick = true;
  dragState = { obj, record, moved: false, startX: e.clientX, startY: e.clientY };
  viewer.context.toggleCameraControls(false);
  container.classList.add('eq-dragging');
});

window.addEventListener('mousemove', (e) => {
  if (!dragState) return;
  if (!dragState.moved) {
    const dx = e.clientX - dragState.startX;
    const dy = e.clientY - dragState.startY;
    if (Math.hypot(dx, dy) < 4) return;
    dragState.moved = true;
  }
  const point = computeDropPoint(e);
  dragState.obj.position.copy(point);
  dragState.record.position = { x: point.x, y: point.y, z: point.z };
  setSelectionHighlight(dragState.obj);
});

window.addEventListener('mouseup', () => {
  if (!dragState) return;
  const { obj, record, moved } = dragState;
  dragState = null;
  viewer.context.toggleCameraControls(true);
  container.classList.remove('eq-dragging');
  selectEquipment(obj);
  if (moved) commitEquipmentChange(record, obj);
});

container.addEventListener('click', async (e) => {
  if (suppressNextClick) {
    suppressNextClick = false;
    return;
  }

  if (armedEquipmentType) {
    const typeId = armedEquipmentType;
    disarmPlacement();
    await placeEquipmentFromDrop(e, typeId);
    return;
  }

  const eqObj = pickEquipmentAt(e);
  if (eqObj) {
    viewer.IFC.selector.unpickIfcItems();
    highlightTreeRow(null);
    selectEquipment(eqObj);
    return;
  }

  if (selectedEquipmentId) {
    selectedEquipmentId = null;
    removeSelectionHighlight();
    renderEquipmentInstances();
  }

  const result = await viewer.IFC.selector.pickIfcItem(false);
  if (!result) {
    clearProperties();
    highlightTreeRow(null);
    return;
  }
  await showIfcProperties(result.modelID, result.id);
  highlightTreeRow(result.id);
});

// ---------- IFC Properties ----------
function unwrap(value) {
  if (value && typeof value === 'object' && 'value' in value) return value.value;
  return value;
}

function clearProperties() {
  propsContent.innerHTML = '<p class="empty-hint">Click an element in the 3D view or the tree to see its properties.</p>';
}

function addRow(parent, key, value) {
  const row = document.createElement('div');
  row.className = 'prop-row';
  const k = document.createElement('div');
  k.className = 'prop-key';
  k.textContent = key;
  const v = document.createElement('div');
  v.className = 'prop-val';
  v.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
  row.appendChild(k);
  row.appendChild(v);
  parent.appendChild(row);
}

function friendlyType(type) {
  if (!type) return '';
  return type.replace(/^IFC/, '');
}

async function showIfcProperties(modelID, expressID) {
  const props = await viewer.IFC.getProperties(modelID, expressID, true, false);
  let ifcClass = '';
  try {
    ifcClass = friendlyType(viewer.IFC.loader.ifcManager.getIfcType(modelID, expressID));
  } catch {
    ifcClass = '';
  }
  propsContent.innerHTML = '';

  const title = document.createElement('div');
  title.className = 'prop-section-title';
  title.textContent = unwrap(props.Name) || ifcClass || `Element #${expressID}`;
  propsContent.appendChild(title);

  const basic = document.createElement('div');
  basic.className = 'prop-section';
  addRow(basic, 'Express ID', expressID);
  addRow(basic, 'IFC Class', ifcClass);
  addRow(basic, 'GlobalId', unwrap(props.GlobalId));
  addRow(basic, 'Name', unwrap(props.Name));
  addRow(basic, 'Object Type', unwrap(props.ObjectType));
  addRow(basic, 'Description', unwrap(props.Description));
  addRow(basic, 'Tag', unwrap(props.Tag));
  propsContent.appendChild(basic);

  if (props.type) {
    const typeSection = document.createElement('div');
    typeSection.className = 'prop-section';
    const t = document.createElement('div');
    t.className = 'prop-section-title';
    t.textContent = 'Type';
    typeSection.appendChild(t);
    addRow(typeSection, 'Name', unwrap(props.type.Name));
    addRow(typeSection, 'Description', unwrap(props.type.Description));
    propsContent.appendChild(typeSection);
  }

  if (Array.isArray(props.psets) && props.psets.length) {
    const psetSection = document.createElement('div');
    psetSection.className = 'prop-section';
    const t = document.createElement('div');
    t.className = 'prop-section-title';
    t.textContent = 'Property Sets';
    psetSection.appendChild(t);

    for (const pset of props.psets) {
      const psetTitle = document.createElement('div');
      psetTitle.className = 'pset-title';
      psetTitle.textContent = unwrap(pset.Name) || 'Property Set';
      psetSection.appendChild(psetTitle);

      const list = pset.HasProperties || pset.Quantities || [];
      for (const p of list) {
        const key = unwrap(p.Name);
        const value = unwrap(p.NominalValue ?? p.LengthValue ?? p.AreaValue ?? p.VolumeValue ?? p.WeightValue ?? p.CountValue);
        addRow(psetSection, key, value);
      }
    }
    propsContent.appendChild(psetSection);
  }
}

// ---------- Spatial tree ----------
async function buildTree(modelID) {
  const structure = await viewer.IFC.getSpatialStructure(modelID, false);
  spatialTreeBody.innerHTML = '';
  const rootEl = renderNode(modelID, structure, 0);
  spatialTreeBody.appendChild(rootEl);
}

function renderNode(modelID, node, depth) {
  const wrapper = document.createElement('div');
  wrapper.className = 'tree-node';

  const row = document.createElement('div');
  row.className = 'tree-row';
  row.dataset.expressId = node.expressID;

  const hasChildren = node.children && node.children.length > 0;

  const caret = document.createElement('span');
  caret.className = 'tree-caret' + (hasChildren ? '' : ' leaf');
  caret.textContent = '▶';
  row.appendChild(caret);

  const label = document.createElement('span');
  label.className = 'tree-label';
  label.textContent = `${friendlyType(node.type)} #${node.expressID}`;
  row.appendChild(label);

  wrapper.appendChild(row);

  let childrenEl = null;
  if (hasChildren) {
    childrenEl = document.createElement('div');
    childrenEl.className = 'tree-children' + (depth >= 1 ? ' collapsed' : '');
    if (depth < 1) caret.classList.add('expanded');
    for (const child of node.children) {
      childrenEl.appendChild(renderNode(modelID, child, depth + 1));
    }
    wrapper.appendChild(childrenEl);

    caret.addEventListener('click', (e) => {
      e.stopPropagation();
      childrenEl.classList.toggle('collapsed');
      caret.classList.toggle('expanded');
    });
  }

  row.addEventListener('click', async () => {
    if (selectedEquipmentId) {
      selectedEquipmentId = null;
      removeSelectionHighlight();
      renderEquipmentInstances();
    }
    highlightTreeRow(node.expressID);
    await viewer.IFC.selector.pickIfcItemsByID(modelID, [node.expressID], true);
    await showIfcProperties(modelID, node.expressID);
  });

  return wrapper;
}

function highlightTreeRow(expressID) {
  if (selectedRow) selectedRow.classList.remove('selected');
  selectedRow = null;
  if (expressID == null) return;
  const row = spatialTreeBody.querySelector(`.tree-row[data-express-id="${expressID}"]`);
  if (row) {
    row.classList.add('selected');
    row.scrollIntoView({ block: 'nearest' });
    selectedRow = row;
  }
}

// ---------- Server models ----------
async function refreshServerModelsUI() {
  if (!backendAvailable) {
    serverModelsListEl.innerHTML = '<p class="empty-hint">Backend not connected. Models &amp; equipment are saved in this browser only.</p>';
    return;
  }
  try {
    const list = await listModels();
    if (!list.length) {
      serverModelsListEl.innerHTML = '<p class="empty-hint">No models saved on the server yet.</p>';
      return;
    }
    serverModelsListEl.innerHTML = '';
    for (const m of list) {
      const row = document.createElement('div');
      row.className = 'server-model-row' + (m.id === currentServerModelId ? ' selected' : '');

      const name = document.createElement('span');
      name.className = 'server-model-name';
      name.textContent = m.name;
      name.title = m.name;

      const loadBtn = document.createElement('button');
      loadBtn.textContent = 'Load';
      loadBtn.addEventListener('click', () => loadModelFromServer(m.id, m.name));

      const delBtn = document.createElement('button');
      delBtn.textContent = '✕';
      delBtn.title = 'Delete from server';
      delBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete "${m.name}" and its saved equipment from the server?`)) return;
        try {
          await deleteModelOnServer(m.id);
          if (currentServerModelId === m.id) currentServerModelId = null;
          refreshServerModelsUI();
        } catch (err) {
          console.error(err);
          alert('Could not delete this model from the server.');
        }
      });

      row.appendChild(name);
      row.appendChild(loadBtn);
      row.appendChild(delBtn);
      serverModelsListEl.appendChild(row);
    }
  } catch (err) {
    console.error(err);
    serverModelsListEl.innerHTML = '<p class="empty-hint">Could not reach the backend.</p>';
  }
}

btnRefreshModels.addEventListener('click', refreshServerModelsUI);

btnSaveModelServer.addEventListener('click', async () => {
  if (!currentLocalFile) return;
  btnSaveModelServer.disabled = true;
  btnSaveModelServer.textContent = 'Saving…';
  try {
    const record = await uploadModel(currentLocalFile);
    currentServerModelId = record.id;
    btnSaveModelServer.hidden = true;
    await refreshServerModelsUI();
  } catch (err) {
    console.error(err);
    alert('Could not save this model to the server.');
  } finally {
    btnSaveModelServer.disabled = false;
    btnSaveModelServer.textContent = 'Save Current Model to Server';
  }
});

// ---------- Dashboard ----------
btnDashboard.addEventListener('click', openDashboard);
btnCloseDashboard.addEventListener('click', closeDashboard);
dashboardOverlay.addEventListener('click', (e) => {
  if (e.target === dashboardOverlay) closeDashboard();
});

function closeDashboard() {
  dashboardOverlay.classList.add('hidden');
}

async function openDashboard() {
  dashboardOverlay.classList.remove('hidden');
  dashboardBody.innerHTML = '<p class="empty-hint">Loading…</p>';

  if (!backendAvailable) {
    dashboardBody.innerHTML =
      '<p class="empty-hint">ต้องเชื่อมต่อ backend (FastAPI + PostgreSQL) เพื่อดู Dashboard ภาพรวมสุขภาพเครื่องจักร</p>';
    return;
  }

  try {
    const summary = await getDashboardSummary();
    renderDashboard(summary);
  } catch (err) {
    console.error('Failed to load dashboard summary', err);
    dashboardBody.innerHTML = '<p class="empty-hint">โหลดข้อมูล Dashboard ไม่สำเร็จ</p>';
  }
}

function makeStatTile(value, label, band) {
  const tile = document.createElement('div');
  tile.className = 'stat-tile' + (band ? ` band-${band}` : '');
  const num = document.createElement('div');
  num.className = 'stat-num';
  num.textContent = String(value);
  const lbl = document.createElement('div');
  lbl.className = 'stat-label';
  lbl.textContent = label;
  tile.appendChild(num);
  tile.appendChild(lbl);
  return tile;
}

function renderDashboard(summary) {
  dashboardBody.innerHTML = '';

  if (!summary.total) {
    dashboardBody.innerHTML = '<p class="empty-hint">ยังไม่มีเครื่องจักรที่บันทึกไว้ในระบบ</p>';
    return;
  }

  const stats = document.createElement('div');
  stats.className = 'dashboard-stats';
  stats.appendChild(makeStatTile(summary.total, 'Total Equipment', ''));
  stats.appendChild(makeStatTile(summary.average_score, 'Avg Score', ''));
  stats.appendChild(makeStatTile(summary.by_band.good || 0, 'Good', 'good'));
  stats.appendChild(makeStatTile(summary.by_band.warning || 0, 'Warning', 'warning'));
  stats.appendChild(makeStatTile(summary.by_band.critical || 0, 'Critical', 'critical'));
  dashboardBody.appendChild(stats);

  const dist = document.createElement('div');
  dist.className = 'dashboard-distribution';
  for (const band of ['good', 'warning', 'critical']) {
    const count = summary.by_band[band] || 0;
    if (!count) continue;
    const seg = document.createElement('div');
    seg.className = `dist-seg band-${band}`;
    seg.style.width = `${(count / summary.total) * 100}%`;
    seg.title = `${band}: ${count}`;
    dist.appendChild(seg);
  }
  dashboardBody.appendChild(dist);

  const table = document.createElement('table');
  table.className = 'dashboard-table';
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr><th></th><th>Name</th><th>Model</th><th>Score</th><th>Status</th><th></th></tr>';
  table.appendChild(thead);

  const tbody = document.createElement('tbody');
  const sorted = [...summary.equipment].sort((a, b) => a.score - b.score);
  for (const item of sorted) {
    const type = EQUIPMENT_TYPES.find((t) => t.id === item.type);
    const tr = document.createElement('tr');

    const iconTd = document.createElement('td');
    iconTd.textContent = type ? type.icon : '❔';
    const nameTd = document.createElement('td');
    nameTd.textContent = item.name;
    const modelTd = document.createElement('td');
    modelTd.textContent = item.model_name || '—';
    const scoreTd = document.createElement('td');
    scoreTd.className = `dash-score band-${item.band}`;
    scoreTd.textContent = String(item.score);
    const statusTd = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = `dash-badge band-${item.band}`;
    badge.textContent = item.band;
    statusTd.appendChild(badge);
    const viewTd = document.createElement('td');
    const viewBtn = document.createElement('button');
    viewBtn.className = 'dash-view-btn';
    viewBtn.textContent = 'View';
    viewBtn.addEventListener('click', () => viewEquipmentFromDashboard(item));
    viewTd.appendChild(viewBtn);

    tr.appendChild(iconTd);
    tr.appendChild(nameTd);
    tr.appendChild(modelTd);
    tr.appendChild(scoreTd);
    tr.appendChild(statusTd);
    tr.appendChild(viewTd);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  dashboardBody.appendChild(table);
}

async function viewEquipmentFromDashboard(item) {
  closeDashboard();

  if (item.model_id !== currentServerModelId) {
    if (item.model_id) {
      await loadModelFromServer(item.model_id, item.model_name || 'Model');
    } else {
      currentServerModelId = null;
      currentModelName = null;
      currentModelID = null;
      currentLocalFile = null;
      modelNameEl.textContent = '';
      btnSaveModelServer.hidden = true;
      spatialTreeBody.innerHTML = '<p class="empty-hint">No model loaded yet.</p>';
      await loadEquipmentForScope();
      refreshServerModelsUI();
    }
  }

  const obj = equipmentObjects.get(item.id);
  if (obj) {
    selectEquipment(obj);
    focusCameraOn(obj);
  }
}

function focusCameraOn(obj) {
  try {
    const controls = viewer.context.getIfcCamera().cameraControls;
    const box = new THREE.Box3().setFromObject(obj);
    controls.fitToBox(box, true, { paddingLeft: 2, paddingRight: 2, paddingTop: 2, paddingBottom: 2 }).catch(() => {});
  } catch (err) {
    console.warn('Could not focus camera on equipment', err);
  }
}

// ---------- Placeable type lookup (equipment + trees) ----------
function isTreeType(typeId) {
  return typeof typeId === 'string' && typeId.startsWith('tree_');
}

function findTypeDef(typeId) {
  return EQUIPMENT_TYPES.find((t) => t.id === typeId) || TREE_TYPES.find((t) => t.id === typeId);
}

// ---------- Equipment / tree libraries (drag source + click-to-place) ----------
function renderTypeLibrary(libraryEl, types) {
  libraryEl.innerHTML = '';
  for (const type of types) {
    const card = document.createElement('div');
    card.className = 'eq-card';
    card.draggable = true;
    card.dataset.typeId = type.id;
    card.innerHTML = `<span class="eq-icon">${type.icon}</span><span class="eq-label">${type.label}</span>`;
    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData(EQ_MIME, type.id);
      e.dataTransfer.setData('text/plain', type.id);
      e.dataTransfer.effectAllowed = 'copy';
      disarmPlacement();
    });
    card.addEventListener('click', () => {
      if (armedEquipmentType === type.id) {
        disarmPlacement();
      } else {
        armPlacement(type.id);
      }
    });
    libraryEl.appendChild(card);
  }
}

function renderEquipmentLibrary() {
  renderTypeLibrary(equipmentLibraryEl, EQUIPMENT_TYPES);
}

function renderTreeLibrary() {
  renderTypeLibrary(treeLibraryEl, TREE_TYPES);
}

function armPlacement(typeId) {
  armedEquipmentType = typeId;
  const type = findTypeDef(typeId);
  document.querySelectorAll('.eq-card').forEach((c) => {
    c.classList.toggle('armed', c.dataset.typeId === typeId);
  });
  eqPlaceHintTextEl.textContent = `Click on the 3D view to place: ${type ? type.label : typeId}`;
  eqPlaceHintEl.hidden = false;
  container.classList.add('eq-armed');
}

function disarmPlacement() {
  armedEquipmentType = null;
  document.querySelectorAll('.eq-card').forEach((c) => c.classList.remove('armed'));
  eqPlaceHintEl.hidden = true;
  container.classList.remove('eq-armed');
}

btnCancelPlace.addEventListener('click', disarmPlacement);

window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && armedEquipmentType) disarmPlacement();
});

// ---------- Equipment placement / raycasting ----------
function ndcFromEvent(e) {
  const rect = container.getBoundingClientRect();
  return new THREE.Vector2(
    ((e.clientX - rect.left) / rect.width) * 2 - 1,
    -((e.clientY - rect.top) / rect.height) * 2 + 1
  );
}

function computeDropPoint(e) {
  const ndc = ndcFromEvent(e);
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndc, viewer.context.getCamera());

  const models = viewer.context.items.pickableIfcModels;
  if (models && models.length) {
    const hits = raycaster.intersectObjects(models, true);
    if (hits.length) return hits[0].point;
  }

  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const point = new THREE.Vector3();
  if (raycaster.ray.intersectPlane(groundPlane, point)) return point;
  return new THREE.Vector3(0, 0, 0);
}

function findEquipmentRoot(object) {
  let o = object;
  while (o) {
    if (o.userData && o.userData.equipmentId) return o;
    o = o.parent;
  }
  return null;
}

function pickEquipmentAt(e) {
  if (equipmentGroup.children.length === 0) return null;
  const ndc = ndcFromEvent(e);
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(ndc, viewer.context.getCamera());
  const hits = raycaster.intersectObject(equipmentGroup, true);
  for (const hit of hits) {
    const root = findEquipmentRoot(hit.object);
    if (root) return root;
  }
  return null;
}

// ---------- Record <-> server payload mapping ----------
function serverToLocalRecord(rec) {
  return {
    id: rec.id,
    type: rec.type,
    name: rec.name,
    position: { x: rec.pos_x, y: rec.pos_y, z: rec.pos_z },
    rotationY: rec.rotation_y || 0,
    scale: rec.scale || 1,
    notes: rec.notes || '',
    status: rec.status || 'running',
    lastMaintenanceDate: rec.last_maintenance_date || null,
    operatingHours: rec.operating_hours || 0,
    temperatureC: rec.temperature_c,
    vibrationMmS: rec.vibration_mm_s,
    serverBacked: true,
  };
}

function localRecordToServerPatch(record) {
  return {
    name: record.name,
    pos_x: record.position.x,
    pos_y: record.position.y,
    pos_z: record.position.z,
    rotation_y: record.rotationY,
    scale: record.scale,
    notes: record.notes,
    status: record.status,
    last_maintenance_date: record.lastMaintenanceDate,
    operating_hours: record.operatingHours,
    temperature_c: record.temperatureC,
    vibration_mm_s: record.vibrationMmS,
  };
}

function makeLocalOnlyRecord(typeId, name, point) {
  return {
    id: uuid(),
    type: typeId,
    name,
    position: { x: point.x, y: point.y, z: point.z },
    rotationY: 0,
    scale: 1,
    notes: '',
    status: 'running',
    lastMaintenanceDate: null,
    operatingHours: 0,
    temperatureC: null,
    vibrationMmS: null,
    serverBacked: false,
  };
}

async function placeEquipmentFromDrop(e, typeId) {
  const point = computeDropPoint(e);
  const type = findTypeDef(typeId);
  const baseName = type ? type.label : typeId;

  if (backendAvailable) {
    try {
      const serverRec = await createEquipmentOnServer({
        model_id: currentServerModelId,
        type: typeId,
        name: baseName,
        pos_x: point.x,
        pos_y: point.y,
        pos_z: point.z,
        rotation_y: 0,
        scale: 1,
        notes: '',
      });
      const obj = instantiateEquipmentObject(serverToLocalRecord(serverRec));
      selectEquipment(obj);
      return;
    } catch (err) {
      console.error('Failed to save equipment to the server, placing locally instead.', err);
    }
  }

  const record = makeLocalOnlyRecord(typeId, baseName, point);
  const obj = instantiateEquipmentObject(record);
  persistEquipment();
  selectEquipment(obj);
}

function instantiateEquipmentObject(record) {
  const obj = isTreeType(record.type)
    ? createTreeObject(record.type, record.name)
    : createEquipmentObject(record.type, record.name);
  obj.position.set(record.position.x, record.position.y, record.position.z);
  obj.rotation.y = THREE.MathUtils.degToRad(record.rotationY || 0);
  const scale = record.scale || 1;
  obj.scale.set(scale, scale, scale);
  obj.userData.equipmentId = record.id;

  equipmentGroup.add(obj);
  equipmentObjects.set(record.id, obj);
  if (!placedEquipment.some((r) => r.id === record.id)) {
    placedEquipment.push(record);
  }
  renderEquipmentInstances();
  return obj;
}

async function deleteEquipment(id) {
  const obj = equipmentObjects.get(id);
  const record = placedEquipment.find((r) => r.id === id);
  if (obj) {
    equipmentGroup.remove(obj);
    disposeEquipmentObject(obj);
    equipmentObjects.delete(id);
  }
  const idx = placedEquipment.findIndex((r) => r.id === id);
  if (idx >= 0) placedEquipment.splice(idx, 1);
  if (selectedEquipmentId === id) {
    selectedEquipmentId = null;
    removeSelectionHighlight();
    clearProperties();
  }

  if (backendAvailable && record && record.serverBacked) {
    try {
      await deleteEquipmentOnServer(id);
    } catch (err) {
      console.error('Failed to delete equipment on the server.', err);
    }
  } else {
    persistEquipment();
  }
  renderEquipmentInstances();
}

function clearAllEquipment() {
  for (const obj of equipmentObjects.values()) {
    equipmentGroup.remove(obj);
    disposeEquipmentObject(obj);
  }
  equipmentObjects.clear();
  placedEquipment = [];
  if (selectedEquipmentId) clearProperties();
  selectedEquipmentId = null;
  removeSelectionHighlight();
  renderEquipmentInstances();
}

function setSelectionHighlight(obj) {
  removeSelectionHighlight();
  selectionBoxHelper = new THREE.BoxHelper(obj, 0xffcc33);
  viewer.context.getScene().add(selectionBoxHelper);
}

function removeSelectionHighlight() {
  if (selectionBoxHelper) {
    viewer.context.getScene().remove(selectionBoxHelper);
    selectionBoxHelper.geometry.dispose();
    selectionBoxHelper.material.dispose();
    selectionBoxHelper = null;
  }
}

function selectEquipment(obj) {
  selectedEquipmentId = obj.userData.equipmentId;
  setSelectionHighlight(obj);
  const record = placedEquipment.find((r) => r.id === selectedEquipmentId);
  if (record) showEquipmentProperties(record, obj);
  renderEquipmentInstances();
}

function renderInstanceList(listEl, records, emptyMessage) {
  listEl.innerHTML = '';
  if (!records.length) {
    listEl.innerHTML = `<p class="empty-hint">${emptyMessage}</p>`;
    return;
  }
  for (const record of records) {
    const type = findTypeDef(record.type);
    const row = document.createElement('div');
    row.className = 'eq-instance-row' + (record.id === selectedEquipmentId ? ' selected' : '');

    const icon = document.createElement('span');
    icon.className = 'eq-instance-icon';
    icon.textContent = type ? type.icon : '❔';

    const name = document.createElement('span');
    name.className = 'eq-instance-name';
    name.textContent = record.name;

    const delBtn = document.createElement('button');
    delBtn.className = 'eq-del-btn';
    delBtn.textContent = '✕';
    delBtn.title = 'Remove';
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteEquipment(record.id);
    });

    row.appendChild(icon);
    row.appendChild(name);
    row.appendChild(delBtn);
    row.addEventListener('click', () => {
      const obj = equipmentObjects.get(record.id);
      if (obj) selectEquipment(obj);
    });

    listEl.appendChild(row);
  }
}

function renderEquipmentInstances() {
  renderInstanceList(equipmentInstancesEl, placedEquipment.filter((r) => !isTreeType(r.type)), 'No equipment placed yet.');
  renderInstanceList(treeInstancesEl, placedEquipment.filter((r) => isTreeType(r.type)), 'No trees planted yet.');
}

// ---------- Equipment properties form ----------
function makeFormRow(labelText, inputEl) {
  const row = document.createElement('div');
  row.className = 'prop-row';
  const label = document.createElement('div');
  label.className = 'prop-key';
  label.textContent = labelText;
  const valWrap = document.createElement('div');
  valWrap.className = 'prop-val';
  valWrap.appendChild(inputEl);
  row.appendChild(label);
  row.appendChild(valWrap);
  return row;
}

function makeTextInput(value, onChange) {
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'eq-input';
  input.value = value;
  input.addEventListener('change', () => onChange(input.value));
  return input;
}

function makeNumberInput(value, onChange, step) {
  const input = document.createElement('input');
  input.type = 'number';
  input.className = 'eq-input';
  input.step = step ?? 0.01;
  input.value = Number(value).toFixed(3);
  input.addEventListener('change', () => onChange(parseFloat(input.value) || 0));
  return input;
}

function makeOptionalNumberInput(value, onChange, step) {
  const input = document.createElement('input');
  input.type = 'number';
  input.className = 'eq-input';
  input.step = step ?? 0.1;
  input.placeholder = 'ไม่มีข้อมูล';
  input.value = value === null || value === undefined ? '' : value;
  input.addEventListener('change', () => {
    onChange(input.value === '' ? null : parseFloat(input.value));
  });
  return input;
}

function makeSelectInput(value, options, onChange) {
  const select = document.createElement('select');
  select.className = 'eq-input';
  for (const [val, labelText] of options) {
    const opt = document.createElement('option');
    opt.value = val;
    opt.textContent = labelText;
    if (val === value) opt.selected = true;
    select.appendChild(opt);
  }
  select.addEventListener('change', () => onChange(select.value));
  return select;
}

function makeDateInput(value, onChange) {
  const input = document.createElement('input');
  input.type = 'date';
  input.className = 'eq-input';
  input.value = value || '';
  input.addEventListener('change', () => onChange(input.value || null));
  return input;
}

async function commitEquipmentChange(record, obj) {
  if (backendAvailable && record.serverBacked) {
    try {
      await updateEquipmentOnServer(record.id, localRecordToServerPatch(record));
    } catch (err) {
      console.error('Failed to sync equipment change to the server.', err);
    }
  } else {
    persistEquipment();
  }
  renderEquipmentInstances();
  showEquipmentProperties(record, obj);
}

function afterFieldChange(record, obj) {
  setSelectionHighlight(obj);
  commitEquipmentChange(record, obj);
}

function showEquipmentProperties(record, obj) {
  const isTree = isTreeType(record.type);
  propsContent.innerHTML = '';

  const title = document.createElement('div');
  title.className = 'prop-section-title';
  title.textContent = `${isTree ? 'Tree' : 'Equipment'}: ${record.name}`;
  propsContent.appendChild(title);

  if (!isTree) renderHealthSection(propsContent, record);

  const form = document.createElement('div');
  form.className = 'prop-section';

  form.appendChild(
    makeFormRow(
      'Name',
      makeTextInput(record.name, (val) => {
        record.name = val || record.name;
        if (isTree) updateTreeLabel(obj, record.name);
        else updateEquipmentLabel(obj, record.name);
        afterFieldChange(record, obj);
      })
    )
  );

  const type = findTypeDef(record.type);
  const typeStatic = document.createElement('span');
  typeStatic.textContent = type ? type.label : record.type;
  form.appendChild(makeFormRow('Type', typeStatic));

  form.appendChild(
    makeFormRow(
      'Position X (m)',
      makeNumberInput(record.position.x, (val) => {
        record.position.x = val;
        obj.position.x = val;
        afterFieldChange(record, obj);
      })
    )
  );
  form.appendChild(
    makeFormRow(
      'Position Y (m)',
      makeNumberInput(record.position.y, (val) => {
        record.position.y = val;
        obj.position.y = val;
        afterFieldChange(record, obj);
      })
    )
  );
  form.appendChild(
    makeFormRow(
      'Position Z (m)',
      makeNumberInput(record.position.z, (val) => {
        record.position.z = val;
        obj.position.z = val;
        afterFieldChange(record, obj);
      })
    )
  );
  form.appendChild(
    makeFormRow(
      'Rotation Y (°)',
      makeNumberInput(
        record.rotationY || 0,
        (val) => {
          record.rotationY = val;
          obj.rotation.y = THREE.MathUtils.degToRad(val);
          afterFieldChange(record, obj);
        },
        1
      )
    )
  );
  form.appendChild(
    makeFormRow(
      'Scale',
      makeNumberInput(
        record.scale || 1,
        (val) => {
          const s = val > 0 ? val : 1;
          record.scale = s;
          obj.scale.set(s, s, s);
          afterFieldChange(record, obj);
        },
        0.1
      )
    )
  );

  propsContent.appendChild(form);

  const notesSection = document.createElement('div');
  notesSection.className = 'prop-section';
  const notesLabel = document.createElement('div');
  notesLabel.className = 'prop-key';
  notesLabel.textContent = 'Notes';
  const notesArea = document.createElement('textarea');
  notesArea.className = 'eq-notes';
  notesArea.value = record.notes || '';
  notesArea.addEventListener('change', () => {
    record.notes = notesArea.value;
    afterFieldChange(record, obj);
  });
  notesSection.appendChild(notesLabel);
  notesSection.appendChild(notesArea);
  propsContent.appendChild(notesSection);

  if (!isTree) {
  const condSection = document.createElement('div');
  condSection.className = 'prop-section';
  const condTitle = document.createElement('div');
  condTitle.className = 'prop-section-title';
  condTitle.textContent = 'Condition Data';
  condSection.appendChild(condTitle);

  condSection.appendChild(
    makeFormRow(
      'Status',
      makeSelectInput(
        record.status || 'running',
        [
          ['running', 'Running'],
          ['stopped', 'Stopped'],
          ['maintenance', 'Maintenance'],
          ['fault', 'Fault'],
        ],
        (val) => {
          record.status = val;
          afterFieldChange(record, obj);
        }
      )
    )
  );
  condSection.appendChild(
    makeFormRow(
      'Last Maintenance',
      makeDateInput(record.lastMaintenanceDate, (val) => {
        record.lastMaintenanceDate = val;
        afterFieldChange(record, obj);
      })
    )
  );
  condSection.appendChild(
    makeFormRow(
      'Operating Hours',
      makeNumberInput(
        record.operatingHours || 0,
        (val) => {
          record.operatingHours = val;
          afterFieldChange(record, obj);
        },
        1
      )
    )
  );
  condSection.appendChild(
    makeFormRow(
      'Temperature (°C)',
      makeOptionalNumberInput(
        record.temperatureC,
        (val) => {
          record.temperatureC = val;
          afterFieldChange(record, obj);
        },
        0.5
      )
    )
  );
  condSection.appendChild(
    makeFormRow(
      'Vibration (mm/s)',
      makeOptionalNumberInput(
        record.vibrationMmS,
        (val) => {
          record.vibrationMmS = val;
          afterFieldChange(record, obj);
        },
        0.1
      )
    )
  );
  propsContent.appendChild(condSection);
  }

  if (isEditable) {
    const delBtn = document.createElement('button');
    delBtn.className = 'btn btn-danger';
    delBtn.textContent = isTree ? 'Delete Tree' : 'Delete Equipment';
    delBtn.addEventListener('click', () => deleteEquipment(record.id));
    propsContent.appendChild(delBtn);
  } else {
    propsContent.querySelectorAll('input, select, textarea').forEach((el) => {
      el.disabled = true;
    });
  }
}

const BAND_COLORS = { good: '#4ade80', warning: '#facc15', critical: '#f87171' };

function makeDonutChart(score, band) {
  const size = 84;
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);
  const color = BAND_COLORS[band] || '#9aa0ac';
  const svgNS = 'http://www.w3.org/2000/svg';

  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svg.classList.add('donut-chart');

  const track = document.createElementNS(svgNS, 'circle');
  track.setAttribute('cx', size / 2);
  track.setAttribute('cy', size / 2);
  track.setAttribute('r', radius);
  track.setAttribute('fill', 'none');
  track.setAttribute('stroke', 'rgba(255,255,255,0.1)');
  track.setAttribute('stroke-width', stroke);
  svg.appendChild(track);

  const progress = document.createElementNS(svgNS, 'circle');
  progress.setAttribute('cx', size / 2);
  progress.setAttribute('cy', size / 2);
  progress.setAttribute('r', radius);
  progress.setAttribute('fill', 'none');
  progress.setAttribute('stroke', color);
  progress.setAttribute('stroke-width', stroke);
  progress.setAttribute('stroke-linecap', 'round');
  progress.setAttribute('stroke-dasharray', circumference);
  progress.setAttribute('stroke-dashoffset', offset);
  progress.setAttribute('transform', `rotate(-90 ${size / 2} ${size / 2})`);
  svg.appendChild(progress);

  const text = document.createElementNS(svgNS, 'text');
  text.setAttribute('x', '50%');
  text.setAttribute('y', '50%');
  text.setAttribute('text-anchor', 'middle');
  text.setAttribute('dominant-baseline', 'central');
  text.setAttribute('fill', color);
  text.classList.add('donut-score-text');
  text.textContent = String(score);
  svg.appendChild(text);

  return svg;
}

async function renderHealthSection(parent, record) {
  const section = document.createElement('div');
  section.className = 'prop-section health-section';
  const title = document.createElement('div');
  title.className = 'prop-section-title';
  title.textContent = 'Health Score';
  section.appendChild(title);

  if (!backendAvailable) {
    const note = document.createElement('p');
    note.className = 'empty-hint';
    note.textContent = 'ต้องเชื่อมต่อ backend (FastAPI + PostgreSQL) เพื่อดู Health Score และคำแนะนำ';
    section.appendChild(note);
    parent.appendChild(section);
    return;
  }
  if (!record.serverBacked) {
    const note = document.createElement('p');
    note.className = 'empty-hint';
    note.textContent = 'อุปกรณ์นี้ยังไม่ได้บันทึกลงเซิร์ฟเวอร์ (โหมด offline) จึงยังไม่มี Health Score';
    section.appendChild(note);
    parent.appendChild(section);
    return;
  }

  const loading = document.createElement('p');
  loading.className = 'empty-hint';
  loading.textContent = 'กำลังคำนวณ Health Score…';
  section.appendChild(loading);
  parent.appendChild(section);

  try {
    const health = await getEquipmentHealth(record.id);
    section.innerHTML = '';
    section.appendChild(title);

    const scoreRow = document.createElement('div');
    scoreRow.className = `health-score-row band-${health.band}`;
    scoreRow.appendChild(makeDonutChart(health.score, health.band));
    const label = document.createElement('div');
    label.className = 'health-score-label';
    label.textContent = health.summary;
    scoreRow.appendChild(label);
    section.appendChild(scoreRow);

    for (const m of health.metrics) {
      const row = document.createElement('div');
      row.className = 'prop-row';
      const k = document.createElement('div');
      k.className = 'prop-key';
      k.textContent = m.label;
      const v = document.createElement('div');
      v.className = `prop-val metric-band-${m.band}`;
      v.textContent = m.value === null || m.value === undefined ? 'ไม่มีข้อมูล' : `${m.value}${m.unit ? ' ' + m.unit : ''}`;
      row.appendChild(k);
      row.appendChild(v);
      section.appendChild(row);
    }

    if (health.recommendations.length) {
      const recTitle = document.createElement('div');
      recTitle.className = 'pset-title';
      recTitle.textContent = 'คำแนะนำ';
      section.appendChild(recTitle);
      const list = document.createElement('ul');
      list.className = 'health-recommendations';
      for (const r of health.recommendations) {
        const li = document.createElement('li');
        li.textContent = r;
        list.appendChild(li);
      }
      section.appendChild(list);
    }
  } catch (err) {
    console.error('Failed to load health score', err);
    section.innerHTML = '';
    section.appendChild(title);
    const errEl = document.createElement('p');
    errEl.className = 'empty-hint';
    errEl.textContent = 'โหลด Health Score ไม่สำเร็จ';
    section.appendChild(errEl);
  }
}

// ---------- Equipment loading for the current model scope ----------
async function loadEquipmentForScope() {
  clearAllEquipment();

  if (backendAvailable) {
    try {
      const serverRecords = await listEquipmentOnServer(currentServerModelId);
      serverRecords.map(serverToLocalRecord).forEach((r) => instantiateEquipmentObject(r));
      return;
    } catch (err) {
      console.error('Failed to load equipment from the server; falling back to this browser only.', err);
    }
  }

  let raw = null;
  try {
    raw = localStorage.getItem(storageKeyFor(currentModelName));
  } catch (err) {
    console.warn('Could not read saved equipment layout.', err);
  }
  if (!raw) return;
  try {
    const records = JSON.parse(raw);
    if (Array.isArray(records)) {
      records.map(normalizeLocalRecord).forEach((r) => instantiateEquipmentObject(r));
    }
  } catch (err) {
    console.warn('Saved equipment layout was corrupted and could not be loaded.', err);
  }
}

// ---------- Local-only persistence (fallback when backend is unavailable) ----------
function storageKeyFor(name) {
  return `ifcviewer:equipment:${name || 'default'}`;
}

function persistEquipment() {
  try {
    localStorage.setItem(storageKeyFor(currentModelName), JSON.stringify(placedEquipment));
  } catch (err) {
    console.warn('Could not save equipment layout to this browser.', err);
  }
}

function normalizeLocalRecord(r) {
  const type = findTypeDef(r.type) || EQUIPMENT_TYPES[0];
  return {
    id: r.id || uuid(),
    type: type.id,
    name: r.name || type.label,
    position: {
      x: Number(r.position?.x) || 0,
      y: Number(r.position?.y) || 0,
      z: Number(r.position?.z) || 0,
    },
    rotationY: Number(r.rotationY) || 0,
    scale: Number(r.scale) || 1,
    notes: r.notes || '',
    status: r.status || 'running',
    lastMaintenanceDate: r.lastMaintenanceDate || null,
    operatingHours: Number(r.operatingHours) || 0,
    temperatureC: r.temperatureC ?? null,
    vibrationMmS: r.vibrationMmS ?? null,
    serverBacked: false,
  };
}

// ---------- Export / import layout (local JSON backup) ----------
function exportLayout() {
  const payload = {
    model: currentModelName || null,
    exportedAt: new Date().toISOString(),
    equipment: placedEquipment,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  const baseName = currentModelName ? currentModelName.replace(/\.ifc$/i, '') : 'layout';
  a.href = url;
  a.download = `equipment-${baseName}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

btnExportLayout.addEventListener('click', exportLayout);
btnExportLayoutTrees.addEventListener('click', exportLayout);

btnImportLayout.addEventListener('click', () => layoutFileInput.click());
btnImportLayoutTrees.addEventListener('click', () => layoutFileInput.click());

layoutFileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  layoutFileInput.value = '';
  if (!file) return;
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const records = Array.isArray(data) ? data : data.equipment;
    if (!Array.isArray(records)) throw new Error('Invalid layout file: missing "equipment" array.');

    if (backendAvailable) {
      for (const existing of placedEquipment) {
        if (existing.serverBacked) {
          try {
            await deleteEquipmentOnServer(existing.id);
          } catch (err) {
            console.error('Failed to remove existing equipment before import.', err);
          }
        }
      }
    }
    clearAllEquipment();

    if (backendAvailable) {
      for (const r of records.map(normalizeLocalRecord)) {
        try {
          const serverRec = await createEquipmentOnServer({
            model_id: currentServerModelId,
            type: r.type,
            name: r.name,
            pos_x: r.position.x,
            pos_y: r.position.y,
            pos_z: r.position.z,
            rotation_y: r.rotationY,
            scale: r.scale,
            notes: r.notes,
            status: r.status,
            last_maintenance_date: r.lastMaintenanceDate,
            operating_hours: r.operatingHours,
            temperature_c: r.temperatureC,
            vibration_mm_s: r.vibrationMmS,
          });
          instantiateEquipmentObject(serverToLocalRecord(serverRec));
        } catch (err) {
          console.error('Failed to import one equipment item to the server.', err);
        }
      }
    } else {
      records.map(normalizeLocalRecord).forEach((r) => instantiateEquipmentObject(r));
      persistEquipment();
    }
  } catch (err) {
    console.error(err);
    alert('Could not import this layout file. Check the console for details.');
  }
});

// ---------- Resize handling ----------
window.addEventListener('resize', () => viewer.context.updateAspect());

// ---------- Init ----------
renderEquipmentLibrary();
renderTreeLibrary();

(async () => {
  backendAvailable = await checkBackendStatus();
  await refreshServerModelsUI();
  await loadEquipmentForScope();
})();
