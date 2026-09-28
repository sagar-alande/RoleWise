"use client";

import { useState } from "react";
import { Button, Card, Field } from "@/components/ui";
import type { Contact } from "@/lib/api";

export function ContactCard({
  contact,
  contactSaved,
  onSave,
  onDirty,
}: {
  contact: Contact;
  contactSaved: boolean;
  onSave: (e: React.FormEvent<HTMLFormElement>) => void;
  onDirty: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Card className="border-slate-100 bg-slate-50/60">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <div>
          <h2 className="font-medium text-slate-700">Optional profile settings</h2>
          <p className="text-xs text-slate-500">Used for tailored resumes and cover letters.</p>
        </div>
        <span className="text-sm text-slate-400">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <form onSubmit={onSave} onChange={onDirty} className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <Field label="Full name" name="full_name" value={contact.full_name} />
          <Field label="Email" name="email" value={contact.email} />
          <Field label="Phone (optional)" name="phone" value={contact.phone} />
          <Field label="City, state or country" name="location" value={contact.location} />
          <div className="sm:col-span-2">
            <Field label="Links, comma separated (LinkedIn, GitHub, portfolio)" name="links" value={contact.links.join(", ")} />
          </div>
          <div className="flex items-center gap-3 sm:col-span-2">
            <Button type="submit" variant="secondary">
              Save contact details
            </Button>
            {contactSaved && <span className="text-sm text-emerald-700">Saved</span>}
          </div>
        </form>
      )}
    </Card>
  );
}
