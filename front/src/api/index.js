export function getData() {
  return fetch("/api/")
    .then(res => res.json())
}
