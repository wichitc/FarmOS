const API_BASE = 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore - body wasn't JSON
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function checkBackendStatus(timeoutMs = 2000) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(`${API_BASE}/api/status`, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadModel(file) {
  const form = new FormData();
  form.append('file', file, file.name);
  const res = await fetch(`${API_BASE}/api/models`, { method: 'POST', body: form });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

export function listModels() {
  return request('/api/models');
}

export function deleteModelOnServer(id) {
  return request(`/api/models/${id}`, { method: 'DELETE' });
}

export function modelFileUrl(id) {
  return `${API_BASE}/api/models/${id}/file`;
}

export function listEquipmentOnServer(modelId) {
  const qs = modelId ? `?model_id=${encodeURIComponent(modelId)}` : '';
  return request(`/api/equipment${qs}`);
}

export function createEquipmentOnServer(payload) {
  return request('/api/equipment', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateEquipmentOnServer(id, payload) {
  return request(`/api/equipment/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteEquipmentOnServer(id) {
  return request(`/api/equipment/${id}`, { method: 'DELETE' });
}

export function getEquipmentHealth(id) {
  return request(`/api/equipment/${id}/health`);
}

export function getDashboardSummary() {
  return request('/api/dashboard/summary');
}
