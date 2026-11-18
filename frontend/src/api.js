async function req(path, opts = {}) {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const detail = (data && data.detail) || text || r.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

export const api = {
  dashboard: () => req('/dashboard'),
  campaigns: () => req('/campaigns'),
  events: (day) => req('/events' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  addEvent: (body) => req('/events', { method: 'POST', body: JSON.stringify(body) }),
  facts: (day) => req('/facts' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  buffer: (day) => req('/redeem/buffer' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  flush: (body = {}) => req('/redeem/flush', { method: 'POST', body: JSON.stringify(body) }),
  preview: (day) => req('/redeem/preview' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  seal: (body) => req('/redeem/seal', { method: 'POST', body: JSON.stringify(body) }),
  batches: () => req('/batches'),
  batch: (id) => req('/batches/' + id),
  getDay: () => req('/settings/day'),
  setDay: (business_day) => req('/settings/day', { method: 'PUT', body: JSON.stringify({ business_day }) }),
  getSealPolicy: () => req('/settings/seal-policy'),
  setSealPolicy: (policy) => req('/settings/seal-policy', { method: 'PUT', body: JSON.stringify({ policy }) }),
  bufferRows: (day) => req('/redeem/buffer' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
}
