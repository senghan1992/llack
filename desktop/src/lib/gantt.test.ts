import { describe, expect, it } from "vitest";
import { dayStart, monthCells, monthStartOf, nextDay, ratio } from "./gantt";

describe("monthCells", () => {
  it("covers the months a span holds, and stops at its end", () => {
    const cells = monthCells(new Date(2026, 10, 1), new Date(2027, 2, 1));
    expect(cells.map((cell) => cell.label)).toEqual(["11월", "12월", "1월", "2월"]);
    expect(cells.map((cell) => cell.year)).toEqual([2026, 2026, 2027, 2027]);
  });

  it("leaves the month the span ends in out when the span ends on its first day", () => {
    const cells = monthCells(new Date(2026, 11, 1), new Date(2027, 0, 1));
    expect(cells.map((cell) => cell.label)).toEqual(["12월"]);
  });

  it("gives every month the length it really has", () => {
    const cells = monthCells(new Date(2027, 0, 1), new Date(2027, 2, 1));
    expect(cells[0].end - cells[0].start).toBe(
      new Date(2027, 1, 1).getTime() - new Date(2027, 0, 1).getTime(),
    );
    expect(cells[1].end - cells[1].start).toBe(
      new Date(2027, 2, 1).getTime() - new Date(2027, 1, 1).getTime(),
    );
  });

  it("butts each month against the next one", () => {
    const cells = monthCells(new Date(2026, 10, 1), new Date(2027, 2, 1));
    for (let index = 1; index < cells.length; index += 1) {
      expect(cells[index].start).toBe(cells[index - 1].end);
    }
  });
});

describe("ratio", () => {
  it("puts the ends of the span at the ends of the chart", () => {
    expect(ratio(100, 100, 200)).toBe(0);
    expect(ratio(200, 100, 200)).toBe(1);
    expect(ratio(150, 100, 200)).toBe(0.5);
  });

  it("keeps a bar that falls outside the span inside the chart", () => {
    expect(ratio(50, 100, 200)).toBe(0);
    expect(ratio(250, 100, 200)).toBe(1);
  });

  it("does not divide by a span of no length", () => {
    expect(ratio(120, 100, 100)).toBe(0);
  });
});

describe("the day a thing falls on", () => {
  it("counts from the reader's own midnight", () => {
    const start = dayStart("2026-11-06T00:00:00.000Z");
    const date = new Date(start);
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
  });

  it("gives a one-day period a width", () => {
    expect(nextDay("2026-11-06T23:59:59.000Z")).toBeGreaterThan(
      dayStart("2026-11-06T00:00:00.000Z"),
    );
  });

  it("opens a month on its first day", () => {
    const start = monthStartOf(new Date(2026, 10, 20).getTime());
    expect(start.getFullYear()).toBe(2026);
    expect(start.getMonth()).toBe(10);
    expect(start.getDate()).toBe(1);
  });
});
