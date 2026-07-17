import { ConversationDetail, ConversationSummary } from "@/features/agent/types";

type ConversationLike = ConversationSummary | ConversationDetail | null | undefined;

export interface BossConversationInfo {
  isBoss: boolean;
  name: string;
  displayName: string;
  role: string;
  age: string;
  education: string;
  school: string;
  experience: string;
  currentCompany: string;
  currentTitle: string;
  expectation: string;
  profileLines: string[];
  subtitle: string;
}

const readLabel = (notes: string, labels: string[]) => {
  for (const label of labels) {
    const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const value = notes.match(new RegExp(`^${escaped}[:：]\\s*(.+)$`, "m"))?.[1]?.trim();
    if (value) {
      return value;
    }
  }
  return "";
};

const normalizeName = (value: string) => {
  const cleaned = value.split(" · ")[0]?.trim() ?? "";
  if (/^BOSS Desktop OCR\b/i.test(cleaned)) {
    return "";
  }
  return cleaned;
};

const firstMatch = (text: string, patterns: RegExp[]) => {
  for (const pattern of patterns) {
    const value = text.match(pattern)?.[1]?.trim();
    if (value) {
      return value;
    }
  }
  return "";
};

const educationFromText = (text: string) =>
  firstMatch(text, [/(博士|硕士|本科|大专|高中|中专|初中)/]);

const schoolFromLines = (lines: string[]) => {
  const schoolLine = lines.find((line) =>
    /(大学|学院|学校|高中|中学|中专)/.test(line)
  );
  if (!schoolLine) {
    return "";
  }
  const withoutDate = schoolLine.replace(/^\d{4}(?:[.-]\d{1,2})?[-至~到]+\d{4}(?:[.-]\d{1,2})?\s*/, "");
  return withoutDate.split(/[·|]/)[0]?.trim() || "";
};

export function parseBossConversation(
  conversation: ConversationLike,
  detail?: ConversationLike
): BossConversationInfo {
  const source = detail ?? conversation;
  const notes = detail?.notes ?? conversation?.notes ?? "";
  const isBoss =
    source?.website === "BOSS直聘" ||
    source?.referrer?.startsWith("boss://chat/") ||
    /^BOSS候选人[:：]/m.test(notes);

  if (!isBoss) {
    return {
      isBoss: false,
      name: "",
      displayName: "",
      role: "",
      age: "",
      education: "",
      school: "",
      experience: "",
      currentCompany: "",
      currentTitle: "",
      expectation: "",
      profileLines: [],
      subtitle: "",
    };
  }

  const name = normalizeName(readLabel(notes, ["BOSS候选人"]));
  const role = readLabel(notes, ["沟通岗位", "沟通职位"]);
  const profileLines = notes
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^(BOSS候选人|沟通岗位|沟通职位)[:：]/.test(line));
  const profileText = profileLines.join("\n");
  const displayName = name || (role ? `${role}候选人` : "BOSS候选人");
  const subtitle = ["BOSS直聘", role].filter(Boolean).join(" · ");

  return {
    isBoss: true,
    name,
    displayName,
    role,
    age: readLabel(notes, ["年龄"]) || firstMatch(profileText, [/(\d{2}\s*岁)/]),
    education: readLabel(notes, ["学历"]) || educationFromText(profileText),
    school: readLabel(notes, ["学校"]) || schoolFromLines(profileLines),
    experience:
      readLabel(notes, ["经验", "工作经验"]) ||
      firstMatch(profileText, [/(\d{2}年应届生)/, /(\d{1,2}\s*年以上)/, /(\d{1,2}\s*年(?:经验)?)/]),
    currentCompany: readLabel(notes, ["最近公司"]),
    currentTitle: readLabel(notes, ["最近职位"]),
    expectation: readLabel(notes, ["期望"]),
    profileLines,
    subtitle,
  };
}
