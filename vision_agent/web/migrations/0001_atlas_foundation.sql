CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  organization_type text NOT NULL CHECK (organization_type IN ('food_bank','vendor','logistics','platform')),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  display_name text NOT NULL,
  global_role text NOT NULL DEFAULT 'member' CHECK (global_role IN ('member','administrator')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS organization_memberships (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  user_id uuid NOT NULL REFERENCES users(id),
  role text NOT NULL CHECK (role IN ('contributor','reviewer','vendor_representative','logistics_coordinator','administrator')),
  site_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, user_id, role, site_id)
);

CREATE TABLE IF NOT EXISTS invitations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  email text NOT NULL,
  role text NOT NULL,
  site_id uuid,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  invited_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  name text NOT NULL,
  county text NOT NULL,
  state text NOT NULL DEFAULT 'CA',
  latitude double precision NOT NULL,
  longitude double precision NOT NULL,
  safety_stock_policy jsonb NOT NULL DEFAULT '{}',
  shortage_threshold numeric NOT NULL DEFAULT 0.15,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE organization_memberships
  DROP CONSTRAINT IF EXISTS organization_memberships_site_id_fkey;
ALTER TABLE organization_memberships
  ADD CONSTRAINT organization_memberships_site_id_fkey FOREIGN KEY (site_id) REFERENCES sites(id);

CREATE TABLE IF NOT EXISTS agents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid REFERENCES organizations(id),
  site_id uuid REFERENCES sites(id),
  agent_type text NOT NULL CHECK (agent_type IN ('site','vendor','logistics','orchestrator')),
  name text NOT NULL,
  configuration jsonb NOT NULL DEFAULT '{}',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id uuid NOT NULL REFERENCES agents(id),
  trigger_type text NOT NULL,
  trigger_reference text,
  status text NOT NULL CHECK (status IN ('running','completed','failed','awaiting_human')),
  input jsonb NOT NULL DEFAULT '{}',
  output jsonb NOT NULL DEFAULT '{}',
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS agent_tool_calls (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_run_id uuid NOT NULL REFERENCES agent_runs(id),
  tool_name text NOT NULL,
  input jsonb NOT NULL,
  output jsonb,
  status text NOT NULL CHECK (status IN ('started','completed','failed')),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS negotiations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger_type text NOT NULL,
  status text NOT NULL CHECK (status IN ('draft','negotiating','awaiting_approvals','approved','reserved','dispatched','received','rejected','expired','cancelled','failed')),
  region text,
  expires_at timestamptz NOT NULL,
  created_by_agent_run_id uuid REFERENCES agent_runs(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  negotiation_id uuid NOT NULL REFERENCES negotiations(id),
  sender_agent_id uuid NOT NULL REFERENCES agents(id),
  recipient_agent_id uuid REFERENCES agents(id),
  recipient_scope text,
  message_type text NOT NULL CHECK (message_type IN ('supply_request','supply_offer','counteroffer','logistics_check','logistics_offer','proposal','acceptance','rejection','escalation','cancellation')),
  payload jsonb NOT NULL,
  parent_message_id uuid REFERENCES agent_messages(id),
  agent_run_id uuid NOT NULL REFERENCES agent_runs(id),
  explanation text NOT NULL,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','accepted','rejected','expired','cancelled')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (recipient_agent_id IS NOT NULL OR recipient_scope IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS vendor_supply (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  category text NOT NULL,
  product_name text,
  available_quantity numeric NOT NULL CHECK (available_quantity >= 0),
  unit text NOT NULL DEFAULT 'units',
  minimum_lot numeric NOT NULL DEFAULT 1,
  pickup_start timestamptz NOT NULL,
  pickup_end timestamptz NOT NULL,
  constraints jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available','partially_reserved','reserved','expired','withdrawn')),
  version integer NOT NULL DEFAULT 1,
  published_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS demand_forecasts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id uuid NOT NULL REFERENCES sites(id),
  category text NOT NULL,
  baseline_demand numeric NOT NULL,
  observed_recent_demand numeric NOT NULL,
  weather_adjustment numeric NOT NULL,
  forecast_demand numeric NOT NULL,
  confidence numeric NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  horizon_hours integer NOT NULL,
  components jsonb NOT NULL DEFAULT '{}',
  source text NOT NULL,
  valid_from timestamptz NOT NULL,
  valid_until timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  site_id uuid NOT NULL REFERENCES sites(id),
  category text NOT NULL,
  product_name text,
  quantity numeric NOT NULL CHECK (quantity > 0),
  unit text NOT NULL DEFAULT 'units',
  direction text NOT NULL CHECK (direction IN ('in','out','hold','release')),
  transaction_type text NOT NULL CHECK (transaction_type IN ('intake','dispatch','transfer_out','transfer_in','manual_adjustment','reservation','reservation_release')),
  source text NOT NULL,
  yolo_model_version text,
  detection_count integer,
  average_confidence numeric,
  source_image_reference text,
  operator_id uuid NOT NULL REFERENCES users(id),
  approval_status text NOT NULL DEFAULT 'pending' CHECK (approval_status IN ('pending','approved','rejected')),
  reviewer_id uuid REFERENCES users(id),
  transfer_proposal_id uuid,
  idempotency_key text NOT NULL UNIQUE,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz
);

CREATE TABLE IF NOT EXISTS inventory_reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  site_id uuid REFERENCES sites(id),
  vendor_supply_id uuid REFERENCES vendor_supply(id),
  category text NOT NULL,
  quantity numeric NOT NULL CHECK (quantity > 0),
  status text NOT NULL CHECK (status IN ('provisional','active','released','consumed','expired')),
  transfer_proposal_id uuid NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((site_id IS NOT NULL)::integer + (vendor_supply_id IS NOT NULL)::integer = 1)
);

CREATE TABLE IF NOT EXISTS routes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_site_id uuid REFERENCES sites(id),
  to_site_id uuid REFERENCES sites(id),
  distance_miles numeric NOT NULL,
  drive_minutes integer NOT NULL,
  refrigerated_capable boolean NOT NULL DEFAULT false,
  constraints jsonb NOT NULL DEFAULT '{}',
  UNIQUE (from_site_id, to_site_id)
);

CREATE TABLE IF NOT EXISTS transportation_capacity (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  vehicle_reference text NOT NULL,
  capacity_units numeric NOT NULL,
  refrigerated boolean NOT NULL DEFAULT false,
  available_from timestamptz NOT NULL,
  available_until timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'available' CHECK (status IN ('available','provisionally_held','assigned','unavailable')),
  constraints jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS transfer_proposals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  negotiation_id uuid NOT NULL REFERENCES negotiations(id),
  status text NOT NULL CHECK (status IN ('draft','negotiating','awaiting_approvals','approved','reserved','dispatched','received','rejected','expired','cancelled','failed')),
  category text NOT NULL,
  requested_quantity numeric NOT NULL,
  optimizer_recommended_quantity numeric NOT NULL,
  human_approved_quantity numeric,
  needed_by timestamptz NOT NULL,
  calculation jsonb NOT NULL,
  plan jsonb NOT NULL,
  version integer NOT NULL DEFAULT 1,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE inventory_transactions
  DROP CONSTRAINT IF EXISTS inventory_transactions_transfer_proposal_id_fkey;
ALTER TABLE inventory_transactions
  ADD CONSTRAINT inventory_transactions_transfer_proposal_id_fkey FOREIGN KEY (transfer_proposal_id) REFERENCES transfer_proposals(id);
ALTER TABLE inventory_reservations
  DROP CONSTRAINT IF EXISTS inventory_reservations_transfer_proposal_id_fkey;
ALTER TABLE inventory_reservations
  ADD CONSTRAINT inventory_reservations_transfer_proposal_id_fkey FOREIGN KEY (transfer_proposal_id) REFERENCES transfer_proposals(id);

CREATE TABLE IF NOT EXISTS proposal_participants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transfer_proposal_id uuid NOT NULL REFERENCES transfer_proposals(id),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  participant_role text NOT NULL CHECK (participant_role IN ('requester','donor','vendor','logistics','receiver')),
  commitment jsonb NOT NULL,
  UNIQUE (transfer_proposal_id, organization_id, participant_role)
);

CREATE TABLE IF NOT EXISTS required_approvals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transfer_proposal_id uuid NOT NULL REFERENCES transfer_proposals(id),
  organization_id uuid NOT NULL REFERENCES organizations(id),
  approval_role text NOT NULL CHECK (approval_role IN ('site_reviewer','vendor_representative','logistics_coordinator','administrator')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
  decision_by uuid REFERENCES users(id),
  decision_note text,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (transfer_proposal_id, organization_id, approval_role)
);

CREATE TABLE IF NOT EXISTS shipments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  transfer_proposal_id uuid NOT NULL UNIQUE REFERENCES transfer_proposals(id),
  status text NOT NULL CHECK (status IN ('planned','reserved','dispatched','in_transit','received','cancelled','failed')),
  logistics_organization_id uuid NOT NULL REFERENCES organizations(id),
  vehicle_reference text,
  pickup_window_start timestamptz NOT NULL,
  pickup_window_end timestamptz NOT NULL,
  delivery_window_start timestamptz NOT NULL,
  delivery_window_end timestamptz NOT NULL,
  manifest jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shipment_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  shipment_id uuid NOT NULL REFERENCES shipments(id),
  event_type text NOT NULL CHECK (event_type IN ('created','reserved','dispatched','picked_up','in_transit','delivered','received','exception','cancelled')),
  actor_user_id uuid REFERENCES users(id),
  actor_agent_run_id uuid REFERENCES agent_runs(id),
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_negotiation ON agent_messages(negotiation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_position ON inventory_transactions(site_id, category, approval_status);
CREATE INDEX IF NOT EXISTS idx_reservations_position ON inventory_reservations(site_id, category, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reservation_site_proposal ON inventory_reservations(transfer_proposal_id, site_id, category) WHERE site_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_reservation_vendor_proposal ON inventory_reservations(transfer_proposal_id, vendor_supply_id, category) WHERE vendor_supply_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_approvals_proposal ON required_approvals(transfer_proposal_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_open_request_dedupe ON agent_messages (
  negotiation_id, sender_agent_id, message_type, ((payload->>'category'))
) WHERE message_type = 'supply_request' AND status = 'active';
