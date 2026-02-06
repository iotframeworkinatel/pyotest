export const containerColors = {
  scanner: "text-green-400",
  http: "text-yellow-300",
  ftp: "text-blue-400",
  mqtt: "text-purple-300",
  telnet: "text-pink-400",
  modbus: "text-orange-400",
  coap: "text-cyan-300",
  dashboard_ui: "text-gray-400",
  h2o: "text-cyan-400",
};

export function colorizeLog(logs) {
  return logs
    .split("\n")
    .map((line) => {
      const match = line.match(/=== \[(.*?)\] ===/);
      if (match) {
        const name = match[1];
        const key = Object.keys(containerColors).find((k) =>
          name.startsWith(k)
        );
        const color = containerColors[key] || "text-white";
        return `<span class="${color} font-semibold">${line}</span>`;
      }
      return `<span class="text-gray-300">${line}</span>`;
    })
    .join("\n");
}
