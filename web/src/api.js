export async function fetchMockData() {
  // Simulate network latency of 300ms to mimic a real API server
  await new Promise(resolve => setTimeout(resolve, 300));
  
  const res = await fetch('/mockData.json');
  if (!res.ok) {
    throw new Error('Failed to load operational data from backend');
  }
  return await res.json();
}
