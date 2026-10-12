import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldAlert, Camera, Clock, UserCheck, AlertTriangle } from 'lucide-react';
import { ClipPlayer } from '../ui/ClipPlayer';
import { apiFetch } from '../../api/client';
import type { EventDetail as EventDetailType } from '../../types';

export default function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [event, setEvent] = useState<EventDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    apiFetch<EventDetailType>(`/api/events/${id}`)
      .then((data) => {
        setEvent(data);
        setError(null);
      })
      .catch((err) => {
        setError(err.message || 'Failed to load event details');
      })
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="p-6 max-w-5xl mx-auto space-y-6 animate-pulse">
        <div className="h-6 w-32 bg-muted rounded" />
        <div className="h-10 w-64 bg-muted rounded" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="aspect-video bg-muted rounded-xl" />
          <div className="h-64 bg-muted rounded-xl" />
        </div>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="p-6 max-w-2xl mx-auto text-center space-y-4">
        <AlertTriangle className="w-12 h-12 text-destructive mx-auto" />
        <h2 className="text-xl font-bold">Event Not Found</h2>
        <p className="text-muted-foreground">{error || `No event records found with ID #${id}`}</p>
        <button
          onClick={() => navigate('/events')}
          className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
        >
          Return to Events Feed
        </button>
      </div>
    );
  }

  const severityBadge = {
    critical: 'bg-destructive/20 text-destructive border-destructive/40',
    warning: 'bg-warning/20 text-warning border-warning/40',
    info: 'bg-primary/20 text-primary border-primary/40',
  }[event.severity];

  const clipSrc = event.clip_local_path ? `/api/events/${event.id}/clip` : event.clip_remote_url;

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <button
        onClick={() => navigate('/events')}
        className="flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="w-4 h-4 mr-2" /> Back to Events
      </button>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">Event #{event.id}</h1>
            <span className={`px-3 py-0.5 rounded-full font-bold text-xs border uppercase tracking-wider ${severityBadge}`}>
              {event.severity}
            </span>
          </div>
          <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
            <span className="flex items-center gap-1">
              <Camera className="w-3.5 h-3.5" /> {event.camera_name}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" /> {new Date(event.created_at).toLocaleString()}
            </span>
          </div>
        </div>

        {event.is_suspicious && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-destructive/10 text-destructive rounded-lg border border-destructive/20 text-sm font-medium">
            <ShieldAlert className="w-4 h-4 animate-pulse" /> Threat Alert Triggered
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl overflow-hidden aspect-video flex items-center justify-center bg-black">
            {event.thumbnail_path ? (
              <img
                src={event.thumbnail_path}
                alt={`Event #${event.id} Frame`}
                className="w-full h-full object-contain"
                onError={(e) => {
                  (e.target as HTMLElement).style.display = 'none';
                }}
              />
            ) : (
              <div className="text-muted-foreground text-sm flex items-center gap-2">
                <Camera className="w-5 h-5" /> No snapshot capture available
              </div>
            )}
          </div>
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Video Evidence</h3>
            <ClipPlayer src={clipSrc || null} />
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
            <h2 className="font-bold text-base mb-3 border-b border-border pb-2 flex items-center justify-between">
              <span>Scene Intelligence & Analysis</span>
              {event.confidence !== null && event.confidence !== undefined && (
                <span className="text-xs text-muted-foreground font-normal">
                  Confidence: {(event.confidence * 100).toFixed(0)}%
                </span>
              )}
            </h2>

            <p className="text-sm text-foreground/90 leading-relaxed mb-4">
              {event.llm_description_full || event.llm_description || 'Motion triggered. No detailed AI summary generated for this record.'}
            </p>

            {event.action_recommendation && (
              <div className="mt-3 p-3 bg-muted/50 rounded-lg border border-border text-xs">
                <span className="font-semibold text-foreground">Action Recommended: </span>
                <span className="text-muted-foreground">{event.action_recommendation}</span>
              </div>
            )}
          </div>

          <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
            <h2 className="font-bold text-base mb-3 border-b border-border pb-2 flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-primary" /> Identity & Biometrics
            </h2>
            <div className="space-y-2 text-sm mb-4">
              <div className="flex justify-between py-1 border-b border-border/50 text-xs">
                <span className="text-muted-foreground">Match Status:</span>
                <span className="font-medium">
                  {event.similarity_score !== null && event.similarity_score !== undefined
                    ? `Matched (${(event.similarity_score * 100).toFixed(0)}% similarity)`
                    : 'Unidentified / Unknown'}
                </span>
              </div>
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => navigate('/faces')}
                className="flex-1 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 transition-colors"
              >
                Enroll / Identify Face
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
