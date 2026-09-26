import "@testing-library/jest-dom";

// jsdom 提供 window.localStorage 但 prototype methods 偶发丢失。
// 给一个稳定的内存 storage，保证测试不会因为 undefined 报错。
if (typeof window !== "undefined") {
  const memory: Record<string, string> = {};
  const stub = {
    getItem: (k: string) => (k in memory ? memory[k] : null),
    setItem: (k: string, v: string) => {
      memory[k] = String(v);
    },
    removeItem: (k: string) => {
      delete memory[k];
    },
    clear: () => {
      for (const k of Object.keys(memory)) delete memory[k];
    },
    key: (i: number) => Object.keys(memory)[i] ?? null,
    get length() {
      return Object.keys(memory).length;
    },
  } as Storage;
  const ls = (window as any).localStorage;
  if (!ls || typeof ls.getItem !== "function") {
    Object.defineProperty(window, "localStorage", { value: stub, writable: false, configurable: true });
  }
}
