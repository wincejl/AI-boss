"use client";

import { useEffect, useMemo, useState } from "react";
import rawRegionTree from "province-city-china/dist/level.json";

import { cn } from "@/lib/utils";

interface RegionNode {
  code: string;
  name: string;
  children?: RegionNode[];
}

interface RegionSelectProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  bossMode?: boolean;
}

const REGION_TREE = rawRegionTree as unknown as RegionNode[];

const SELECT_CLASS =
  "h-10 min-w-0 rounded-md border border-input bg-background px-3 text-sm text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2";

function simplifyName(name: string): string {
  return name
    .replace(/特别行政区$/u, "")
    .replace(/维吾尔自治区$/u, "")
    .replace(/壮族自治区$/u, "")
    .replace(/回族自治区$/u, "")
    .replace(/自治区$/u, "")
    .replace(/省$/u, "")
    .replace(/市$/u, "")
    .replace(/区$/u, "")
    .replace(/县$/u, "")
    .trim();
}

function valueMatchesNode(value: string, node: RegionNode): boolean {
  if (!value) return false;
  const simple = simplifyName(node.name);
  return value.includes(node.name) || (simple !== "" && value.includes(simple));
}

function findInitialCodes(value: string): {
  provinceCode: string;
  cityCode: string;
  areaCode: string;
} {
  const empty = { provinceCode: "", cityCode: "", areaCode: "" };
  if (!value.trim()) return empty;

  for (const province of REGION_TREE) {
    if (valueMatchesNode(value, province)) {
      const city = province.children?.find((item) => valueMatchesNode(value, item));
      const area = city?.children?.find((item) => valueMatchesNode(value, item));
      return {
        provinceCode: province.code,
        cityCode: city?.code ?? "",
        areaCode: area?.code ?? "",
      };
    }
  }

  for (const province of REGION_TREE) {
    for (const city of province.children ?? []) {
      if (valueMatchesNode(value, city)) {
        const area = city.children?.find((item) => valueMatchesNode(value, item));
        return {
          provinceCode: province.code,
          cityCode: city.code,
          areaCode: area?.code ?? "",
        };
      }
      for (const area of city.children ?? []) {
        if (valueMatchesNode(value, area)) {
          return {
            provinceCode: province.code,
            cityCode: city.code,
            areaCode: area.code,
          };
        }
      }
    }
  }

  return empty;
}

function buildLocationValue(
  province: RegionNode | undefined,
  city: RegionNode | undefined,
  area: RegionNode | undefined,
  includeProvince = true
): string {
  return [includeProvince ? province?.name : "", city?.name, area?.name].filter(Boolean).join("");
}

export function RegionSelect({ value, onChange, className, bossMode = false }: RegionSelectProps) {
  const initialCodes = useMemo(() => findInitialCodes(value), [value]);
  const [provinceCode, setProvinceCode] = useState(initialCodes.provinceCode);
  const [cityCode, setCityCode] = useState(initialCodes.cityCode);
  const [areaCode, setAreaCode] = useState(initialCodes.areaCode);
  const allCityOptions = useMemo(
    () =>
      REGION_TREE.flatMap((province) =>
        (province.children ?? []).map((city) => ({
          ...city,
          provinceCode: province.code,
        }))
      ),
    []
  );

  useEffect(() => {
    setProvinceCode(initialCodes.provinceCode);
    setCityCode(initialCodes.cityCode);
    setAreaCode(initialCodes.areaCode);
  }, [initialCodes.provinceCode, initialCodes.cityCode, initialCodes.areaCode]);

  const selectedProvince = REGION_TREE.find((item) => item.code === provinceCode);
  const cityOptions = bossMode ? allCityOptions : selectedProvince?.children ?? [];
  const selectedCity = cityOptions.find((item) => item.code === cityCode);
  const areaOptions = selectedCity?.children ?? [];
  const selectedArea = areaOptions.find((item) => item.code === areaCode);

  function emit(nextProvinceCode: string, nextCityCode: string, nextAreaCode: string) {
    const province = REGION_TREE.find((item) => item.code === nextProvinceCode);
    const city = province?.children?.find((item) => item.code === nextCityCode);
    const area = city?.children?.find((item) => item.code === nextAreaCode);
    onChange(buildLocationValue(province, city, area, !bossMode));
  }

  if (bossMode) {
    return (
      <div className={cn("grid min-w-0 gap-2 sm:grid-cols-2", className)}>
        <select
          className={SELECT_CLASS}
          value={cityCode}
          onChange={(event) => {
            const nextCityCode = event.target.value;
            const city = allCityOptions.find((item) => item.code === nextCityCode);
            const nextProvinceCode = city?.provinceCode ?? "";
            setProvinceCode(nextProvinceCode);
            setCityCode(nextCityCode);
            setAreaCode("");
            emit(nextProvinceCode, nextCityCode, "");
          }}
          aria-label="城市"
        >
          <option value="">城市/区县</option>
          {allCityOptions.map((item) => (
            <option key={item.code} value={item.code}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          value={areaCode}
          onChange={(event) => {
            const nextAreaCode = event.target.value;
            setAreaCode(nextAreaCode);
            emit(provinceCode, cityCode, nextAreaCode);
          }}
          disabled={!selectedCity || areaOptions.length === 0}
          aria-label="区县"
        >
          <option value="">区县/镇</option>
          {areaOptions.map((item) => (
            <option key={item.code} value={item.code}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div className={cn("grid min-w-0 gap-2 sm:grid-cols-3", className)}>
      <select
        className={SELECT_CLASS}
        value={provinceCode}
        onChange={(event) => {
          const nextProvinceCode = event.target.value;
          setProvinceCode(nextProvinceCode);
          setCityCode("");
          setAreaCode("");
          emit(nextProvinceCode, "", "");
        }}
        aria-label="省份"
      >
        <option value="">省份</option>
        {REGION_TREE.map((item) => (
          <option key={item.code} value={item.code}>
            {item.name}
          </option>
        ))}
      </select>
      <select
        className={SELECT_CLASS}
        value={cityCode}
        onChange={(event) => {
          const nextCityCode = event.target.value;
          setCityCode(nextCityCode);
          setAreaCode("");
          emit(provinceCode, nextCityCode, "");
        }}
        disabled={!selectedProvince}
        aria-label="城市"
      >
        <option value="">城市/区县</option>
        {cityOptions.map((item) => (
          <option key={item.code} value={item.code}>
            {item.name}
          </option>
        ))}
      </select>
      <select
        className={SELECT_CLASS}
        value={areaCode}
        onChange={(event) => {
          const nextAreaCode = event.target.value;
          setAreaCode(nextAreaCode);
          emit(provinceCode, cityCode, nextAreaCode);
        }}
        disabled={!selectedCity || areaOptions.length === 0}
        aria-label="区县"
      >
        <option value="">区县</option>
        {areaOptions.map((item) => (
          <option key={item.code} value={item.code}>
            {item.name}
          </option>
        ))}
      </select>
    </div>
  );
}
