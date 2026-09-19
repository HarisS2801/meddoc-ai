import type {
  KeyFinding,
  RiskItem,
  StructuredSummary,
} from "../types";

const NOT_MENTIONED = "Not mentioned in the report";

type Tone = "good" | "warn" | "bad" | "info" | "neutral";

const toneStyles: Record<Tone, string> = {
  good: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  warn: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  bad: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  neutral: "border-slate-600/50 bg-slate-700/20 text-slate-300",
};

function Badge({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${toneStyles[tone]}`}
    >
      {label}
    </span>
  );
}

function riskTone(level: string): Tone {
  switch (level.toLowerCase()) {
    case "low concern":
      return "good";
    case "moderate concern":
      return "warn";
    case "high concern":
      return "bad";
    default:
      return "neutral";
  }
}

function severityTone(label: string): Tone {
  const value = label.toLowerCase();
  if (value.includes("well controlled") || value.includes("normal")) return "good";
  if (value.includes("partially") || value.includes("mild")) return "warn";
  if (
    value.includes("poorly") ||
    value.includes("severe") ||
    value.includes("moderate")
  ) {
    return "bad";
  }
  return "neutral";
}

function followUpTone(value: string): Tone {
  switch (value.toLowerCase()) {
    case "yes":
      return "info";
    case "no":
      return "good";
    default:
      return "neutral";
  }
}

function isMissing(value: string | null | undefined): boolean {
  if (!value) return true;
  const lowered = value.trim().toLowerCase();
  return (
    lowered === NOT_MENTIONED.toLowerCase() ||
    lowered === "not available" ||
    lowered === "n/a" ||
    lowered === "unable to determine from the available information" ||
    lowered === "unable to determine from the report"
  );
}

function ValueText({ value }: { value: string }) {
  if (isMissing(value)) {
    return (
      <span className="break-words italic text-slate-500">
        {value || NOT_MENTIONED}
      </span>
    );
  }
  return <span className="break-words text-slate-100">{value}</span>;
}

function Card({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-2xl border border-slate-800 bg-slate-900/50 p-5 ${className}`}
    >
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-teal-300">
        {title}
      </h3>
      {children}
    </section>
  );
}

function StatTile({
  label,
  value,
  tone,
  badge,
}: {
  label: string;
  value: string;
  tone?: Tone;
  badge?: boolean;
}) {
  return (
    <div className="rounded-lg bg-slate-800/50 px-3 py-2">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-0.5 min-w-0 break-words text-sm font-medium">
        {badge ? <Badge label={value} tone={tone} /> : <ValueText value={value} />}
      </dd>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-800/70 py-2 last:border-0">
      <dt className="shrink-0 text-xs text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm">
        <ValueText value={value} />
      </dd>
    </div>
  );
}

function RiskList({ items }: { items: RiskItem[] }) {
  return (
    <ul className="space-y-3">
      {items.map((item, index) => (
        <li
          key={`${item.characteristic}-${index}`}
          className="rounded-lg border border-slate-800 bg-slate-800/30 p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-slate-100">
              {item.characteristic}
            </span>
            <Badge label={item.level} tone={riskTone(item.level)} />
          </div>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="shrink-0 text-xs text-slate-500">Evidence</dt>
              <dd className="text-slate-300">
                {isMissing(item.evidence) ? "—" : item.evidence}
              </dd>
            </div>
            {item.explanation && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-xs text-slate-500">Meaning</dt>
                <dd className="text-slate-300">{item.explanation}</dd>
              </div>
            )}
            {item.recommendation && (
              <div className="flex gap-2">
                <dt className="shrink-0 text-xs text-slate-500">Recommendation</dt>
                <dd className="text-slate-300">{item.recommendation}</dd>
              </div>
            )}
          </dl>
          <p className="mt-2 text-[11px] text-slate-500">
            AI-generated interpretation, not a medical diagnosis.
          </p>
        </li>
      ))}
    </ul>
  );
}

function FindingList({
  items,
  tone,
}: {
  items: KeyFinding[];
  tone: Tone;
}) {
  return (
    <ul className="space-y-2">
      {items.map((item, index) => (
        <li
          key={`${item.finding}-${index}`}
          className="rounded-lg border border-slate-800 bg-slate-800/30 p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-100">
              {item.finding}
            </span>
            {item.value && <Badge label={item.value} tone={tone} />}
          </div>
          {item.why_it_matters && (
            <p className="mt-1.5 text-sm text-slate-400">{item.why_it_matters}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

function StringList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5 text-sm text-slate-300">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

function SectionEmpty({ children }: { children: React.ReactNode }) {
  return <p className="text-sm italic text-slate-500">{children}</p>;
}

export default function StructuredSummaryView({
  data,
}: {
  data: StructuredSummary;
}) {
  const card = data.status_card;
  const info = data.patient_information;
  const condition = data.main_condition;
  const overview = data.document_overview;
  const followUp = data.follow_up;
  const hasFollowUp =
    followUp.follow_up_plan.length > 0 ||
    followUp.monitoring_plan.length > 0 ||
    followUp.precautions.length > 0;

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-teal-600/30 bg-gradient-to-b from-teal-600/10 to-slate-900/40 p-5">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-teal-300">
          Summary at a glance
        </h3>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <StatTile label="Patient" value={card.patient_name} />
          <StatTile label="Main condition" value={card.main_condition} />
          <StatTile label="Report type" value={card.report_type} />
          <StatTile label="Report date" value={card.report_date} />
          <StatTile
            label="Overall status"
            value={card.overall_status}
            tone={severityTone(card.overall_status)}
            badge
          />
          <StatTile
            label="Disease control"
            value={card.disease_control}
            tone={severityTone(card.disease_control)}
            badge
          />
          <StatTile
            label="Abnormal findings"
            value={String(card.abnormal_findings_count)}
          />
          <StatTile
            label="Measurements"
            value={String(card.measurements_count)}
          />
          <StatTile
            label="Follow-up"
            value={card.follow_up_required}
            tone={followUpTone(card.follow_up_required)}
            badge
          />
        </dl>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Patient information">
          <dl className="text-sm">
            <InfoRow label="Name" value={info.name} />
            <InfoRow label="Patient / hospital ID" value={info.patient_id} />
            <InfoRow label="Age" value={info.age} />
            <InfoRow label="Gender" value={info.gender} />
            <InfoRow label="Report date" value={info.report_date} />
            <InfoRow label="Doctor / hospital" value={info.doctor_or_hospital} />
          </dl>
        </Card>

        <Card title="Main medical condition">
          <dl className="text-sm">
            <InfoRow label="Document type" value={overview.document_type} />
            <InfoRow label="Main condition" value={condition.main_condition} />
            <InfoRow label="Status" value={condition.status} />
            <InfoRow label="Purpose of visit / test" value={condition.purpose} />
          </dl>
          {condition.symptoms_or_findings.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs text-slate-500">
                Symptoms / findings mentioned
              </p>
              <StringList items={condition.symptoms_or_findings} />
            </div>
          )}
        </Card>
      </div>

      <Card title="Risk overview">
        {data.risk_overview.length > 0 ? (
          <RiskList items={data.risk_overview} />
        ) : (
          <SectionEmpty>
            Not enough information in the report to assess risk factors.
          </SectionEmpty>
        )}
      </Card>

      <Card title="Key findings">
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-xs font-medium text-amber-200/80">
              Abnormal or important findings
            </p>
            {data.key_findings.abnormal.length > 0 ? (
              <FindingList items={data.key_findings.abnormal} tone="warn" />
            ) : (
              <SectionEmpty>None reported.</SectionEmpty>
            )}
          </div>
          <div>
            <p className="mb-2 text-xs font-medium text-emerald-200/80">
              Normal or reassuring findings
            </p>
            {data.key_findings.normal_or_reassuring.length > 0 ? (
              <FindingList
                items={data.key_findings.normal_or_reassuring}
                tone="good"
              />
            ) : (
              <SectionEmpty>None reported.</SectionEmpty>
            )}
          </div>
        </div>
      </Card>

      <Card title="Medications and treatment">
        {data.medications.length > 0 ? (
          <div className="space-y-3">
            {data.medications.map((medication, index) => (
              <div
                key={`${medication.name}-${index}`}
                className="rounded-lg border border-slate-800 bg-slate-800/30 p-3"
              >
                <p className="text-sm font-semibold text-slate-100">
                  {medication.name}
                </p>
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
                  <InfoRow label="Dosage" value={medication.dosage} />
                  <InfoRow label="Frequency" value={medication.frequency} />
                  <InfoRow label="Duration" value={medication.duration} />
                  <InfoRow label="Reason" value={medication.reason} />
                  <InfoRow label="Changes" value={medication.changes} />
                  <InfoRow label="Follow-up" value={medication.follow_up} />
                </dl>
              </div>
            ))}
          </div>
        ) : (
          <SectionEmpty>
            No medication information was found in this report.
          </SectionEmpty>
        )}
      </Card>

      <Card title="Follow-up and important instructions">
        {hasFollowUp ? (
          <div className="grid gap-4 lg:grid-cols-3">
            <div>
              <p className="mb-2 text-xs font-medium text-slate-400">
                Follow-up plan
              </p>
              {followUp.follow_up_plan.length > 0 ? (
                <StringList items={followUp.follow_up_plan} />
              ) : (
                <SectionEmpty>Not mentioned.</SectionEmpty>
              )}
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-slate-400">
                Monitoring plan
              </p>
              {followUp.monitoring_plan.length > 0 ? (
                <StringList items={followUp.monitoring_plan} />
              ) : (
                <SectionEmpty>Not mentioned.</SectionEmpty>
              )}
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-slate-400">
                Important precautions
              </p>
              {followUp.precautions.length > 0 ? (
                <StringList items={followUp.precautions} />
              ) : (
                <SectionEmpty>Not mentioned.</SectionEmpty>
              )}
            </div>
          </div>
        ) : (
          <SectionEmpty>
            No follow-up instructions were found in this report.
          </SectionEmpty>
        )}
      </Card>

      <Card title="What this means in simple language">
        <p className="min-w-0 break-words whitespace-pre-line text-sm leading-relaxed text-slate-200">
          {data.simple_explanation ||
            "No plain-language explanation was provided."}
        </p>
      </Card>

      <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-200/90">
        {data.safety_notice}
      </p>
    </div>
  );
}
