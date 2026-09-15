import { describe, expect, it } from "vitest";
import { detachedCommand } from "./detachedSpawn";

describe("detachedCommand — desk jobs run in their own systemd scope with a memory ceiling", () => {
  it("wraps the command in systemd-run --scope when available", () => {
    const line = detachedCommand("/repo/.venv/bin/python", ["-m", "pipeline.foresight_snapshot", "--all-verticals"], {
      unit: "foresight snapshot",
      memoryMax: "40G",
      useScope: true,
    });
    expect(line.cmd).toBe("/usr/bin/systemd-run");
    expect(line.args.slice(0, 6)).toEqual(["--user", "--scope", "--quiet", "--collect", "-p", "MemoryMax=40G"]);
    expect(line.args[6]).toMatch(/^--unit=catandary-foresight-snapshot-\d+$/);
    expect(line.args.slice(7)).toEqual(["--", "/repo/.venv/bin/python", "-m", "pipeline.foresight_snapshot", "--all-verticals"]);
  });

  it("falls back to the bare command without systemd-run", () => {
    expect(detachedCommand("py", ["a"], { unit: "x", useScope: false })).toEqual({ cmd: "py", args: ["a"] });
  });
});
