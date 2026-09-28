"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, SectionEyebrow } from "@/components/ui";
import { CareerInformationCard } from "@/components/profile/CareerInformationCard";
import { ContactCard } from "@/components/profile/ContactCard";
import { FITS, KINDS, split } from "@/components/profile/constants";
import { NextStepBanner } from "@/components/profile/NextStepBanner";
import { PreferencesCard } from "@/components/profile/PreferencesCard";
import { ResumeCard } from "@/components/profile/ResumeCard";
import { VerificationStatusCard } from "@/components/profile/VerificationStatusCard";
import { api, waitForRun, type Contact, type Fact, type FactKind, type Preferences, type Resume, type Tier } from "@/lib/api";

export default function OnboardingPage() {
  const router = useRouter();
  const [facts, setFacts] = useState<Fact[]>([]);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [resume, setResume] = useState<Resume | null>(null);
  const [contact, setContact] = useState<Contact | null>(null);
  const [contactSaved, setContactSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingUpload, setPendingUpload] = useState<File | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, p, r, c] = await Promise.all([api.listFacts(), api.getPreferences(), api.getResume(), api.getContact()]);
      setContact(c);
      setFacts(f);
      setPrefs(p);
      setResume(r);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(file: File, replaceExisting = false) {
    setBusy("Reading your resume…");
    setError(null);
    try {
      const { run_id } = await api.uploadResume(file, replaceExisting);
      const run = await waitForRun(run_id);
      if (run.status === "failed") setError(`Parsing failed: ${run.error}`);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  /** Re-uploading over an existing resume needs the user's call: merge with what's already on the
   * profile, or wipe it and start clean from this upload. A brand-new upload has nothing to choose
   * between, so it goes straight through. */
  function chooseFile(file: File) {
    if (resume) {
      setPendingUpload(file);
    } else {
      void upload(file);
    }
  }

  function resolvePendingUpload(replaceExisting: boolean) {
    if (!pendingUpload) return;
    const file = pendingUpload;
    setPendingUpload(null);
    void upload(file, replaceExisting);
  }

  async function resetProfile() {
    setBusy("Resetting your career profile…");
    setError(null);
    try {
      await api.resetProfile();
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  async function saveContact(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      setContact(
        await api.putContact({
          full_name: String(form.get("full_name")).trim(),
          email: String(form.get("email")).trim(),
          phone: String(form.get("phone")).trim(),
          location: String(form.get("location")).trim(),
          links: split(String(form.get("links"))),
        }),
      );
      setContactSaved(true);
    } catch (err) {
      setError(String(err));
    }
  }

  async function addFact(kind: FactKind, title: string, details: Record<string, unknown>) {
    setError(null);
    try {
      await api.createFact({ kind, title, details });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function updateFactYears(id: string, nextYears: string) {
    setError(null);
    try {
      const n = nextYears.trim();
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, years: n ? Number(n) : undefined } });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  /** Highlights feed the tailored resume and cover letter directly (resume_tailor.v1 / cover_letter.v1
   * only draw from a role's verified bullets) - without these, generated documents stay generic even
   * when the role itself is fully verified. */
  async function updateFactHighlights(id: string, highlights: string[]) {
    setError(null);
    try {
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, highlights } });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  /** Company/dates only ever show on a generated resume when they're set here - the resume header
   * pulls them straight from the fact, never invents them. */
  async function updateFactField(id: string, field: string, value: string) {
    setError(null);
    try {
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, [field]: value || undefined } });
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function removeFact(id: string) {
    setError(null);
    try {
      await api.deleteFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  /** Entering years, a company/dates field, or a bullet on an extracted-but-unconfirmed fact is
   * treated as confirming it - the same "yes, this is real" signal as clicking Confirm. */
  async function confirmPendingWithYears(id: string, nextYears: string) {
    const n = nextYears.trim();
    if (!n) return;
    setError(null);
    try {
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, years: Number(n) } });
      await api.verifyFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function confirmPendingField(id: string, field: string, value: string) {
    setError(null);
    try {
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, [field]: value || undefined } });
      await api.verifyFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function confirmPendingHighlights(id: string, highlights: string[]) {
    setError(null);
    try {
      const fact = facts.find((f) => f.id === id);
      await api.updateFact(id, { details: { ...fact?.details, highlights } });
      await api.verifyFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function confirmPending(id: string) {
    setError(null);
    try {
      await api.verifyFact(id);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function savePrefsAndSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!prefs) return;
    setError(null);
    const form = new FormData(e.currentTarget);
    const next: Preferences = {
      ...prefs,
      target_titles: split(String(form.get("target_titles"))),
      locations: split(String(form.get("locations"))),
      remote_modes: form.getAll("remote_modes") as Preferences["remote_modes"],
      salary_min: form.get("salary_min") ? Number(form.get("salary_min")) : null,
      dealbreakers: split(String(form.get("dealbreakers"))),
      excluded_title_keywords: split(String(form.get("excluded_title_keywords"))),
      seniority: (String(form.get("seniority")) || null) as Tier | null,
      skip_tiers: form.getAll("skip_tiers") as Tier[],
      authorized_in: split(String(form.get("authorized_in"))),
      needs_sponsorship: (() => {
        const sponsorship = String(form.get("sponsorship") ?? "");
        return sponsorship === "required" ? true : sponsorship === "not_required" ? false : null;
      })(),
      archetypes: FITS.flatMap(({ fit }) =>
        split(String(form.get(`archetype_${fit}`))).map((name) => ({ name, fit })),
      ),
    };
    setBusy("Saving preferences…");
    try {
      setPrefs(await api.putPreferences(next));
      await findMatches();
    } catch (e) {
      setError(String(e));
      setBusy(null);
    }
  }

  async function findMatches() {
    setError(null);
    setBusy("Searching job boards and scoring matches…");
    try {
      const { run_id } = await api.discoverMatches();
      const run = await waitForRun(run_id, 300_000);
      if (run.status === "failed") {
        setError(`Search failed: ${run.error}`);
        return;
      }
      router.push("/recommendations");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }

  const pending = facts.filter((f) => !f.verified);
  const verified = facts.filter((f) => f.verified);
  const verifiedByKind = KINDS.map((k) => ({ kind: k, items: verified.filter((f) => f.kind === k) })).filter(
    (g) => g.items.length > 0,
  );
  const pendingByKind = KINDS.map((k) => ({ kind: k, items: pending.filter((f) => f.kind === k) })).filter(
    (g) => g.items.length > 0,
  );

  return (
    <div className="space-y-6">
      <div>
        <SectionEyebrow>Your profile</SectionEyebrow>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">Let's build your profile</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Upload your resume, confirm what's true, and set your preferences. RoleWise only uses facts you have
          verified — nothing unverified appears in matches or documents.
        </p>
      </div>

      <ErrorNote error={error} />

      <NextStepBanner hasResume={!!resume} pendingCount={pending.length} verifiedCount={verified.length} />

      <ResumeCard
        resume={resume}
        busy={busy}
        pendingUpload={pendingUpload}
        onChooseFile={chooseFile}
        onResolvePendingUpload={resolvePendingUpload}
        onCancelPendingUpload={() => setPendingUpload(null)}
        onResetProfile={resetProfile}
      />

      <VerificationStatusCard
        pendingByKind={pendingByKind}
        pendingCount={pending.length}
        verifiedCount={verified.length}
        onConfirm={confirmPending}
        onConfirmYears={confirmPendingWithYears}
        onConfirmField={confirmPendingField}
        onConfirmHighlights={confirmPendingHighlights}
        onRemove={removeFact}
      />

      <CareerInformationCard
        verifiedByKind={verifiedByKind}
        onAdd={addFact}
        onUpdateYears={updateFactYears}
        onUpdateField={updateFactField}
        onUpdateHighlights={updateFactHighlights}
        onRemove={removeFact}
      />

      {prefs && <PreferencesCard prefs={prefs} busy={busy} onSave={savePrefsAndSearch} />}

      {contact && (
        <ContactCard
          contact={contact}
          contactSaved={contactSaved}
          onSave={saveContact}
          onDirty={() => setContactSaved(false)}
        />
      )}
    </div>
  );
}
