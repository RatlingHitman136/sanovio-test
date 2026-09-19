import { gs1Valid, sameTradeItem } from "./gs1";

test.each([
  ["04040456789018", true],
  ["04040456789017", false],
  ["4006381333931", true],
  ["96385074", true],
  ["abc", false],
  ["0404045678901", true],
  ["040404567890", false],
  ["404045678901234", false],
])("gs1Valid(%s) is %s", (code, valid) => {
  expect(gs1Valid(code)).toBe(valid);
});

test("only a valid GTIN on both sides makes the same trade item", () => {
  const theirs = [{ scheme: "GTIN", value: "04040456789018" }];
  expect(sameTradeItem([{ scheme: "GTIN", value: "04040456789018" }], theirs)).toBe(
    "04040456789018",
  );
  expect(sameTradeItem([{ scheme: "GTIN", value: "04040456789017" }], theirs)).toBeUndefined();
  expect(sameTradeItem([{ scheme: "EAN", value: "04040456789018" }], theirs)).toBeUndefined();
});
