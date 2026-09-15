import { describe, expect, it } from "vitest";
import { snapshotWorkerArgs } from "./foresightSnapshotWorker";

describe("snapshotWorkerArgs — only the two fixed invocations reach the shell", () => {
  it("maps the two modes to their module invocation", () => {
    expect(snapshotWorkerArgs("clusters")).toEqual(["-m", "pipeline.foresight_snapshot", "--all-verticals", "--dim1024"]);
    expect(snapshotWorkerArgs("lineage")).toEqual(["-m", "pipeline.foresight_snapshot", "--lineage", "--dim1024"]);
  });

  it("rejects anything else, including injected flags", () => {
    expect(snapshotWorkerArgs("")).toBeNull();
    expect(snapshotWorkerArgs("clusters --limit 1")).toBeNull();
    expect(snapshotWorkerArgs("--lineage")).toBeNull();
  });
});
