import type { Feature, FeatureCollection } from "geojson";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { api, getCatalog, getLayer, unwrap, type Schemas } from "../api/client";
import { canEdit, useSession } from "../app/session";
import { ErrorMessage } from "../components/ErrorMessage";
import { label } from "../components/labels";
import { useT } from "../i18n/context";
import { MapView, type MapLayer } from "../map/MapView";
import { edgeStyle, facilityPoint } from "../map/styles";

type Body = Schemas["ScenarioBody"];
type Severity = Schemas["SeverityIn"];
type CapacityChange = Schemas["CapacityChangeIn"];
type NewFacility = Schemas["NewFacilityIn"];
type Mode = "walk" | "car" | "public_transport";

interface Draft {
  name: string;
  description: string;
  visibility: "private" | "shared";
  body: Required<Body>;
}

const EMPTY: Draft = {
  name: "",
  description: "",
  visibility: "private",
  body: {
    schema_version: "1.0",
    capacity_changes: [],
    new_facilities: [],
    network_changes: { edge_changes: [], new_edges: [] },
    population_changes: [],
    severities: [],
    closed_edges: null,
    rationing: null,
    reference_level: null,
  },
};

function normalise(body: Body): Required<Body> {
  return {
    schema_version: "1.0",
    capacity_changes: body.capacity_changes ?? [],
    new_facilities: body.new_facilities ?? [],
    // Placeholders without an editor yet (ADR 0016): kept as they are, so saving never drops them.
    network_changes: body.network_changes ?? { edge_changes: [], new_edges: [] },
    population_changes: body.population_changes ?? [],
    severities: body.severities ?? [],
    closed_edges: body.closed_edges ?? null,
    rationing: body.rationing ?? null,
    reference_level: body.reference_level ?? null,
  };
}

function fid(f: Feature): string {
  return String(f.id ?? "");
}

export function ScenarioEditorPage() {
  const { t } = useT();
  const { scenarioId } = useParams();
  const navigate = useNavigate();
  const { activeDataVersion: dv, config, user } = useSession();
  const [scenario, setScenario] = useState<Schemas["ScenarioOut"] | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [dirty, setDirty] = useState(false);
  const [facilities, setFacilities] = useState<FeatureCollection | null>(null);
  const [edges, setEdges] = useState<FeatureCollection | null>(null);
  const [nodes, setNodes] = useState<FeatureCollection | null>(null);
  const [services, setServices] = useState<Schemas["ServiceOut"][]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [validation, setValidation] = useState<Schemas["ValidationOut"] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [seed, setSeed] = useState(1);
  const [delay, setDelay] = useState("");

  const editable = scenario ? scenario.can_edit : canEdit(user);

  useEffect(() => {
    if (!scenarioId) return;
    unwrap(api.GET("/scenarios/{scenario_id}", { params: { path: { scenario_id: scenarioId } } }))
      .then((s) => {
        setScenario(s);
        setDraft({
          name: s.current.name,
          description: s.current.description,
          visibility: s.visibility,
          body: normalise(s.current.body),
        });
        setDirty(false);
      })
      .catch(setError);
  }, [scenarioId]);

  useEffect(() => {
    if (!dv) return;
    Promise.all([
      getLayer(dv.id, "facilities"),
      getLayer(dv.id, "network_edges"),
      getLayer(dv.id, "network_nodes"),
      getCatalog(dv.id),
    ])
      .then(([f, e, n, c]) => {
        setFacilities(f);
        setEdges(e);
        setNodes(n);
        setServices(c.services);
      })
      .catch(setError);
  }, [dv]);

  // Live validation (debounced): schema and references against the active data version.
  const latest = useRef(0);
  useEffect(() => {
    const id = ++latest.current;
    const timer = window.setTimeout(() => {
      unwrap(api.POST("/scenarios/validate", { body: draft as unknown as Record<string, never> }))
        .then((v) => {
          if (id === latest.current) setValidation(v);
        })
        .catch(setError);
    }, 300);
    return () => {
      window.clearTimeout(timer);
    };
  }, [draft]);

  function update(change: (d: Draft) => Draft) {
    setDraft((d) => change(d));
    setDirty(true);
    setMessage(null);
  }
  function updateBody(change: (b: Required<Body>) => Required<Body>) {
    update((d) => ({ ...d, body: change(d.body) }));
  }

  const closed = new Set(draft.body.closed_edges?.edge_ids ?? []);
  const affected = new Set([
    ...draft.body.severities.map((s) => s.facility_id),
    ...draft.body.capacity_changes.map((c) => c.facility_id),
  ]);

  function toggleEdge(edgeId: string) {
    updateBody((b) => {
      const ids = new Set(b.closed_edges?.edge_ids ?? []);
      if (ids.has(edgeId)) ids.delete(edgeId);
      else ids.add(edgeId);
      const modes: Mode[] = b.closed_edges?.modes ?? ["walk", "car"];
      return { ...b, closed_edges: ids.size ? { edge_ids: [...ids].sort(), modes } : null };
    });
  }

  const mapLayers = useMemo<MapLayer[]>(() => {
    const out: MapLayer[] = [];
    if (edges) {
      out.push({
        id: "edges",
        data: edges,
        style: (f) => edgeStyle(f, closed.has(fid(f))),
        tooltip: (f) => `${fid(f)}${closed.has(fid(f)) ? ` (${t("editor.closed")})` : ""}`,
        ...(editable
          ? {
              onSelect: (f: Feature) => {
                if ((f.properties as { closable?: boolean } | null)?.closable) toggleEdge(fid(f));
              },
            }
          : {}),
      });
    }
    if (facilities) {
      out.push({
        id: "facilities",
        data: facilities,
        point: (f) => facilityPoint(f, affected.has(fid(f)) || selected === fid(f)),
        tooltip: fid,
        onSelect: (f) => {
          setSelected(fid(f));
        },
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- closed/affected derive from draft
  }, [edges, facilities, draft, selected, editable, t]);

  async function save() {
    setError(null);
    try {
      const body = draft as unknown as Schemas["ScenarioIn"];
      const saved = scenario
        ? await unwrap(
            api.PUT("/scenarios/{scenario_id}", {
              params: { path: { scenario_id: scenario.id } },
              body,
            }),
          )
        : await unwrap(api.POST("/scenarios", { body }));
      setScenario(saved);
      setDirty(false);
      setMessage(t("editor.saved", { version: saved.latest_version }));
      if (!scenario) void navigate(`/scenarios/${saved.id}`, { replace: true });
    } catch (e) {
      setError(e);
    }
  }

  async function run() {
    if (!scenario) return;
    setError(null);
    try {
      const created = await unwrap(
        api.POST("/runs", {
          body: {
            scenario_id: scenario.id,
            seed,
            force: false,
            config: delay === "" ? {} : { step_delay_s: Number(delay) },
          },
        }),
      );
      void navigate(`/runs/${created.id}`);
    } catch (e) {
      setError(e);
    }
  }

  const selectedFeature = facilities?.features.find((f) => fid(f) === selected);
  const selectedServices = Object.keys(
    (selectedFeature?.properties as { services?: Record<string, unknown> } | null)?.services ?? {},
  );
  const severity = draft.body.severities.find((s) => s.facility_id === selected);
  const valid = validation?.valid === true;

  return (
    <section aria-labelledby="editor-title">
      <h2 id="editor-title">
        {scenario ? t("editor.title_edit", { name: scenario.name }) : t("editor.title_new")}
      </h2>
      {scenario && (
        <p className="muted">
          {t("editor.version_info", {
            version: scenario.latest_version,
            data: scenario.current.data_version.version,
            owner: scenario.owner ?? t("scenarios.system"),
          })}{" "}
          <Link to="/scenarios">{t("editor.back")}</Link>
        </p>
      )}
      {!editable && <p role="note">{t("editor.read_only")}</p>}
      {scenario && scenario.problems.length > 0 && (
        <div className="banner banner--warning" role="note">
          <p>{t("editor.revalidation", { data: dv?.version ?? "" })}</p>
          <ul>
            {scenario.problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      <fieldset disabled={!editable}>
        <legend>{t("editor.general")}</legend>
        <label>
          {t("editor.name")}
          <input
            name="name"
            value={draft.name}
            onChange={(e) => {
              update((d) => ({ ...d, name: e.target.value }));
            }}
          />
        </label>
        <label>
          {t("editor.description")}
          <textarea
            name="description"
            value={draft.description}
            onChange={(e) => {
              update((d) => ({ ...d, description: e.target.value }));
            }}
          />
        </label>
        <label>
          {t("editor.visibility")}
          <select
            value={draft.visibility}
            onChange={(e) => {
              update((d) => ({ ...d, visibility: e.target.value as Draft["visibility"] }));
            }}
          >
            <option value="private">{label(t, "visibility", "private")}</option>
            <option value="shared">{label(t, "visibility", "shared")}</option>
          </select>
        </label>
        <label>
          {t("editor.rationing")}
          <select
            value={draft.body.rationing ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              updateBody((b) => ({ ...b, rationing: v === "" ? null : (v as "uniform") }));
            }}
          >
            <option value="">{t("editor.none")}</option>
            <option value="uniform">{label(t, "rationing", "uniform")}</option>
            <option value="concentrated">{label(t, "rationing", "concentrated")}</option>
          </select>
        </label>
        <label>
          {t("editor.reference_level")}
          <select
            value={draft.body.reference_level ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              updateBody((b) => ({ ...b, reference_level: v === "" ? null : (v as "minor") }));
            }}
          >
            <option value="">{t("editor.not_reference")}</option>
            <option value="minor">{label(t, "reference", "minor")}</option>
            <option value="moderate">{label(t, "reference", "moderate")}</option>
            <option value="severe">{label(t, "reference", "severe")}</option>
          </select>
        </label>
        <p className="muted">{t("editor.oq_note")}</p>
      </fieldset>

      <div className="map-grid">
        <MapView
          label={t("editor.map_label")}
          layers={mapLayers}
          basemap={config?.basemap ?? "blank"}
        />
        <aside className="panel" aria-live="polite">
          <h3>{t("editor.selected_facility")}</h3>
          {!selected && <p>{t("editor.select_facility_hint")}</p>}
          {selected && (
            <fieldset disabled={!editable}>
              <legend>{selected}</legend>
              <label>
                {t("editor.severity")}
                <input
                  type="number"
                  name="severity"
                  min={0}
                  max={1}
                  step={0.25}
                  value={severity?.severity ?? ""}
                  onChange={(e) => {
                    const raw = e.target.value;
                    updateBody((b) => {
                      const rest = b.severities.filter((s) => s.facility_id !== selected);
                      const next: Severity[] =
                        raw === ""
                          ? rest
                          : [...rest, { facility_id: selected, severity: Number(raw) }];
                      return { ...b, severities: next };
                    });
                  }}
                />
              </label>
              <p className="muted">{t("editor.severity_help")}</p>
              <CapacityForm
                key={selected}
                facility={selected}
                services={selectedServices}
                onAdd={(c) => {
                  updateBody((b) => ({ ...b, capacity_changes: [...b.capacity_changes, c] }));
                }}
              />
            </fieldset>
          )}
        </aside>
      </div>

      <h3>{t("editor.changes")}</h3>
      <ChangeList
        draft={draft}
        editable={editable}
        onRemoveSeverity={(id) => {
          updateBody((b) => ({
            ...b,
            severities: b.severities.filter((s) => s.facility_id !== id),
          }));
        }}
        onRemoveCapacity={(i) => {
          updateBody((b) => ({
            ...b,
            capacity_changes: b.capacity_changes.filter((_, j) => j !== i),
          }));
        }}
        onRemoveNew={(i) => {
          updateBody((b) => ({ ...b, new_facilities: b.new_facilities.filter((_, j) => j !== i) }));
        }}
        onModes={(modes) => {
          updateBody((b) => ({
            ...b,
            closed_edges: b.closed_edges ? { ...b.closed_edges, modes } : null,
          }));
        }}
      />

      <details>
        <summary>{t("editor.facilities_and_edges")}</summary>
        <h4>{t("layer.facilities")}</h4>
        <ul className="feature-list">
          {facilities?.features.map((f) => (
            <li key={fid(f)}>
              <button
                type="button"
                onClick={() => {
                  setSelected(fid(f));
                }}
              >
                {t("editor.select", { id: fid(f) })}
              </button>
            </li>
          ))}
        </ul>
        <h4>{t("layer.network_edges")}</h4>
        <ul className="feature-list">
          {edges?.features.map((f) => {
            const closable = (f.properties as { closable?: boolean } | null)?.closable === true;
            return (
              <li key={fid(f)}>
                <button
                  type="button"
                  disabled={!editable || !closable}
                  onClick={() => {
                    toggleEdge(fid(f));
                  }}
                >
                  {closed.has(fid(f))
                    ? t("editor.reopen_edge", { id: fid(f) })
                    : t("editor.close_edge", { id: fid(f) })}
                </button>
                {!closable && <span className="muted"> {t("editor.not_closable")}</span>}
              </li>
            );
          })}
        </ul>
      </details>

      {editable && nodes && (
        <NewFacilityForm
          nodes={nodes.features.map(fid)}
          services={services.map((s) => s.service_id)}
          onAdd={(n) => {
            updateBody((b) => ({ ...b, new_facilities: [...b.new_facilities, n] }));
          }}
        />
      )}

      <section aria-live="polite" aria-labelledby="validation-title" className="panel">
        <h3 id="validation-title">{t("editor.validation")}</h3>
        {validation === null && <p>{t("editor.validating")}</p>}
        {validation?.valid && <p data-testid="validation-ok">{t("editor.valid")}</p>}
        {validation && !validation.valid && (
          <ul data-testid="validation-errors" className="error">
            {validation.errors.map((e) => (
              <li key={`${e.loc.join(".")}:${e.msg}`}>
                {e.loc.filter((l) => l !== "body").join(" › ")}: {e.msg}
              </li>
            ))}
            {validation.problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
      </section>

      <ErrorMessage error={error} />
      {message && <p role="status">{message}</p>}
      {editable && (
        <p className="actions">
          <button type="button" onClick={() => void save()} disabled={!valid || !dirty}>
            {scenario ? t("editor.save_version") : t("editor.save")}
          </button>
          {scenario && (
            <>
              <label>
                {t("editor.seed")}
                <input
                  type="number"
                  min={0}
                  value={seed}
                  onChange={(e) => {
                    setSeed(Number(e.target.value));
                  }}
                />
              </label>
              <label>
                {t("editor.step_delay")}
                <input
                  type="number"
                  min={0}
                  max={60}
                  step={0.5}
                  placeholder={t("editor.step_delay_default")}
                  value={delay}
                  onChange={(e) => {
                    setDelay(e.target.value);
                  }}
                />
              </label>
              <button type="button" onClick={() => void run()} disabled={dirty || !valid}>
                {t("editor.run")}
              </button>
            </>
          )}
        </p>
      )}
    </section>
  );
}

function CapacityForm({
  facility,
  services,
  onAdd,
}: {
  facility: string;
  services: string[];
  onAdd: (c: CapacityChange) => void;
}) {
  const { t } = useT();
  const [service, setService] = useState(services[0] ?? "");
  const [input, setInput] = useState<CapacityChange["capacity_input"]>("staff");
  const [mode, setMode] = useState<CapacityChange["mode"]>("relative");
  const [amount, setAmount] = useState("20");
  return (
    <div className="subform">
      <h4>{t("editor.capacity_change")}</h4>
      <label>
        {t("editor.service")}
        <select
          value={service}
          onChange={(e) => {
            setService(e.target.value);
          }}
        >
          {services.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        {t("editor.capacity_input")}
        <select
          value={input}
          onChange={(e) => {
            setInput(e.target.value as CapacityChange["capacity_input"]);
          }}
        >
          {(["places", "staff", "throughput"] as const).map((k) => (
            <option key={k} value={k}>
              {label(t, "attr", k)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("editor.mode")}
        <select
          value={mode}
          onChange={(e) => {
            setMode(e.target.value as CapacityChange["mode"]);
          }}
        >
          <option value="relative">{t("editor.relative")}</option>
          <option value="absolute">{t("editor.absolute")}</option>
        </select>
      </label>
      <label>
        {t("editor.amount")}
        <input
          type="number"
          value={amount}
          onChange={(e) => {
            setAmount(e.target.value);
          }}
        />
      </label>
      <button
        type="button"
        disabled={!service || amount === ""}
        onClick={() => {
          onAdd({
            facility_id: facility,
            service_id: service,
            capacity_input: input,
            mode,
            amount: Number(amount),
          });
        }}
      >
        {t("editor.add_change")}
      </button>
    </div>
  );
}

function NewFacilityForm({
  nodes,
  services,
  onAdd,
}: {
  nodes: string[];
  services: string[];
  onAdd: (n: NewFacility) => void;
}) {
  const { t } = useT();
  const [id, setId] = useState("F-NEW-1");
  const [name, setName] = useState("");
  const [node, setNode] = useState(nodes[0] ?? "");
  const [service, setService] = useState(services[0] ?? "");
  const [throughput, setThroughput] = useState("50");
  return (
    <details className="subform">
      <summary>{t("editor.new_facility")}</summary>
      <label>
        {t("editor.facility_id")}
        <input
          value={id}
          onChange={(e) => {
            setId(e.target.value);
          }}
        />
      </label>
      <label>
        {t("editor.facility_name")}
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </label>
      <label>
        {t("editor.node")}
        <select
          value={node}
          onChange={(e) => {
            setNode(e.target.value);
          }}
        >
          {nodes.map((n) => (
            <option key={n}>{n}</option>
          ))}
        </select>
      </label>
      <label>
        {t("editor.service")}
        <select
          value={service}
          onChange={(e) => {
            setService(e.target.value);
          }}
        >
          {services.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label>
        {label(t, "attr", "throughput")}
        <input
          type="number"
          min={0}
          value={throughput}
          onChange={(e) => {
            setThroughput(e.target.value);
          }}
        />
      </label>
      <button
        type="button"
        disabled={!id || !name || !node || !service}
        onClick={() => {
          onAdd({
            facility_id: id,
            name,
            facility_type: "new",
            node_id: node,
            services: [{ service_id: service, throughput: Number(throughput) }],
          });
        }}
      >
        {t("editor.add_facility")}
      </button>
    </details>
  );
}

function ChangeList({
  draft,
  editable,
  onRemoveSeverity,
  onRemoveCapacity,
  onRemoveNew,
  onModes,
}: {
  draft: Draft;
  editable: boolean;
  onRemoveSeverity: (id: string) => void;
  onRemoveCapacity: (index: number) => void;
  onRemoveNew: (index: number) => void;
  onModes: (modes: Mode[]) => void;
}) {
  const { t } = useT();
  const b = draft.body;
  const placeholders =
    (b.network_changes.edge_changes?.length ?? 0) +
    (b.network_changes.new_edges?.length ?? 0) +
    b.population_changes.length;
  const nothing =
    b.severities.length === 0 &&
    b.capacity_changes.length === 0 &&
    b.new_facilities.length === 0 &&
    placeholders === 0 &&
    !b.closed_edges;
  if (nothing) return <p>{t("editor.no_changes")}</p>;
  const modes = b.closed_edges?.modes ?? [];
  return (
    <ul className="change-list" data-testid="change-list">
      {b.severities.map((s) => (
        <li key={`sev-${s.facility_id}`}>
          {t("editor.change_severity", { id: s.facility_id, value: s.severity })}{" "}
          {editable && (
            <button
              type="button"
              onClick={() => {
                onRemoveSeverity(s.facility_id);
              }}
            >
              {t("editor.remove")}
            </button>
          )}
        </li>
      ))}
      {b.capacity_changes.map((c, i) => (
        <li key={`cap-${String(i)}`}>
          {t(c.mode === "relative" ? "editor.change_capacity_rel" : "editor.change_capacity_abs", {
            id: c.facility_id,
            service: c.service_id,
            input: label(t, "attr", c.capacity_input),
            amount: c.amount,
          })}{" "}
          {editable && (
            <button
              type="button"
              onClick={() => {
                onRemoveCapacity(i);
              }}
            >
              {t("editor.remove")}
            </button>
          )}
        </li>
      ))}
      {b.new_facilities.map((n, i) => (
        <li key={`new-${n.facility_id}`}>
          {t("editor.change_new", { id: n.facility_id, node: n.node_id })}{" "}
          {editable && (
            <button
              type="button"
              onClick={() => {
                onRemoveNew(i);
              }}
            >
              {t("editor.remove")}
            </button>
          )}
        </li>
      ))}
      {placeholders > 0 && (
        <li data-testid="recorded-only">
          {t("editor.change_recorded_only", { count: placeholders })}
        </li>
      )}
      {b.closed_edges && (
        <li>
          {t("editor.change_edges", { ids: b.closed_edges.edge_ids.join(", ") })}{" "}
          <fieldset className="inline" disabled={!editable}>
            <legend>{t("editor.closed_for")}</legend>
            {(["walk", "car"] as const).map((m) => (
              <label key={m}>
                <input
                  type="checkbox"
                  checked={modes.includes(m)}
                  onChange={(e) => {
                    onModes(e.target.checked ? [...modes, m] : modes.filter((x) => x !== m));
                  }}
                />{" "}
                {label(t, "mode", m)}
              </label>
            ))}
          </fieldset>
        </li>
      )}
    </ul>
  );
}
