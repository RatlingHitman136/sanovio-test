/**
 * The GS1 mod-10 check digit, as `equivalence_core.identifiers` computes it. The browser needs
 * its own copy: with product hints off, only the client holds both sides' GTINs (§8, D51).
 */
export function gs1Valid(code: string): boolean {
  if (!/^\d{8}$|^\d{12,14}$/.test(code)) return false;
  const digits = Array.from({ length: code.length }, (_, index) => Number(code[index]));
  const check = digits.pop();
  let sum = 0;
  digits.reverse().forEach((digit, index) => {
    sum += digit * (index % 2 === 0 ? 3 : 1);
  });
  return (10 - (sum % 10)) % 10 === check;
}

export interface IdentifierLike {
  scheme: string;
  value: string;
}

/** A check-digit-valid GTIN both sides carry: the same trade item (D51). */
export function sameTradeItem(
  ours: IdentifierLike[],
  theirs: IdentifierLike[],
): string | undefined {
  const gtins = (list: IdentifierLike[]) =>
    new Set(list.filter((id) => id.scheme === "GTIN" && gs1Valid(id.value)).map((id) => id.value));
  const supplier = gtins(theirs);
  return [...gtins(ours)].find((gtin) => supplier.has(gtin));
}
