import React, { useEffect, useState } from 'react';
import { Upload, User, Trash2, Plus, X, Check, ShieldQuestion, AlertCircle } from 'lucide-react';
import { apiFetch } from '../../api/client';
import type { FaceProfile, UnknownCandidate } from '../../types';

export default function Faces() {
  const [faces, setFaces] = useState<FaceProfile[]>([]);
  const [unknowns, setUnknowns] = useState<UnknownCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showEnrollModal, setShowEnrollModal] = useState(false);
  const [enrollName, setEnrollName] = useState('');
  const [enrollFiles, setEnrollFiles] = useState<FileList | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = () => {
    setLoading(true);
    Promise.all([
      apiFetch<FaceProfile[]>('/api/faces').catch(() => []),
      apiFetch<UnknownCandidate[]>('/api/faces/unknown').catch(() => []),
    ])
      .then(([facesData, unknownsData]) => {
        setFaces(facesData || []);
        setUnknowns(unknownsData || []);
      })
      .finally(() => setLoading(false));
  };

  const deleteFace = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to remove this enrolled face profile?')) return;
    apiFetch(`/api/faces/${id}`, { method: 'DELETE' })
      .then(() => {
        setStatusMessage('Profile removed successfully');
        loadData();
      })
      .catch((err) => alert(err.message || 'Failed to delete'));
  };

  const handleEnrollSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enrollName.trim() || !enrollFiles || enrollFiles.length === 0) {
      alert('Please provide a name and at least one photo.');
      return;
    }

    setEnrolling(true);
    const formData = new FormData();
    formData.append('name', enrollName.trim());
    for (let i = 0; i < enrollFiles.length; i++) {
      formData.append('images', enrollFiles[i]);
    }

    try {
      const res = await fetch('/api/faces/enroll', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to enroll');
      }
      setShowEnrollModal(false);
      setEnrollName('');
      setEnrollFiles(null);
      setStatusMessage(`Face profile '${enrollName}' enrolled successfully!`);
      loadData();
    } catch (err: any) {
      alert(err.message || 'Enrollment error');
    } finally {
      setEnrolling(false);
    }
  };

  return (
    <div className="p-6 space-y-8 max-w-7xl mx-auto">
      {statusMessage && (
        <div className="p-3 bg-primary/10 border border-primary/20 text-primary text-sm rounded-lg flex items-center justify-between">
          <span>{statusMessage}</span>
          <button onClick={() => setStatusMessage(null)} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Enrolled Faces Section */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold">Enrolled Face Profiles</h1>
            <p className="text-xs text-muted-foreground">Known individuals recognized by the vision pipeline</p>
          </div>
          <button
            onClick={() => setShowEnrollModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 transition shadow-sm"
          >
            <Plus className="w-4 h-4" /> Enroll New Face
          </button>
        </div>

        {loading ? (
          <div className="text-muted-foreground p-8 text-center animate-pulse">Loading biometric database...</div>
        ) : faces.length === 0 ? (
          <div className="text-muted-foreground p-8 text-center bg-card border border-border rounded-xl">
            No known faces enrolled yet. Click "Enroll New Face" to register individuals.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
            {faces.map((face) => (
              <div
                key={face.id}
                className="bg-card border border-border rounded-xl p-4 text-center flex flex-col items-center relative group shadow-sm hover:border-primary/50 transition-colors"
              >
                <button
                  onClick={(e) => deleteFace(face.id, e)}
                  title="Delete Profile"
                  className="absolute top-2 right-2 p-1.5 bg-destructive text-destructive-foreground rounded-md opacity-0 group-hover:opacity-100 transition shadow"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-3 overflow-hidden border border-border shadow-inner">
                  {face.thumbnail_path ? (
                    <img
                      src={face.thumbnail_path}
                      alt={face.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                    />
                  ) : (
                    <User className="w-8 h-8 text-muted-foreground" />
                  )}
                </div>
                <span className="font-semibold text-sm truncate w-full text-foreground">{face.name}</span>
                <span className="text-xs text-muted-foreground mt-0.5">{face.total_events} events</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* AutoLearner Unknown Candidates Section */}
      <div className="border-t border-border pt-8">
        <div className="mb-4">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <ShieldQuestion className="w-5 h-5 text-warning" /> AutoLearner Candidate Review
          </h2>
          <p className="text-xs text-muted-foreground">
            Frequently detected unknown faces flagged for identity confirmation
          </p>
        </div>

        {unknowns.length === 0 ? (
          <div className="bg-card border border-border rounded-xl p-8 text-center border-dashed">
            <AlertCircle className="mx-auto mb-2 text-muted-foreground w-8 h-8 opacity-50" />
            <p className="text-muted-foreground text-sm mb-1">No unconfirmed frequent candidates right now</p>
            <p className="text-xs text-muted-foreground">
              Argus automatically tracks recurrent unrecognized faces and queues them here for one-click enrollment.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {unknowns.map((candidate) => (
              <div key={candidate.id} className="bg-card border border-border rounded-xl p-4 flex items-center gap-4">
                <div className="w-14 h-14 rounded-lg bg-muted flex items-center justify-center overflow-hidden border border-border shrink-0">
                  {candidate.thumbnail_url ? (
                    <img src={candidate.thumbnail_url} alt="Candidate" className="w-full h-full object-cover" />
                  ) : (
                    <User className="w-6 h-6 text-muted-foreground" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold truncate">Candidate #{candidate.id}</div>
                  <div className="text-xs text-muted-foreground">Spotted {candidate.appearance_count} times</div>
                  <div className="text-[11px] text-muted-foreground mt-0.5">
                    Last: {new Date(candidate.last_seen).toLocaleDateString()}
                  </div>
                </div>
                <button
                  onClick={() => {
                    setEnrollName(`Person_${candidate.id.replace('cam-', '')}`);
                    setShowEnrollModal(true);
                  }}
                  className="px-3 py-1.5 bg-primary/20 hover:bg-primary/30 text-primary rounded-lg text-xs font-semibold transition"
                >
                  Label
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Enroll Modal Dialog */}
      {showEnrollModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-card border border-border rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h3 className="font-bold text-lg">Enroll New Face Profile</h3>
              <button
                onClick={() => setShowEnrollModal(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEnrollSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Full Name / Identifier
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. John Doe, Delivery Driver, Resident"
                  value={enrollName}
                  onChange={(e) => setEnrollName(e.target.value)}
                  className="w-full px-3 py-2 bg-background border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase text-muted-foreground mb-1">
                  Reference Photos
                </label>
                <div className="border-2 border-dashed border-border rounded-xl p-4 text-center cursor-pointer hover:border-primary/50 transition">
                  <Upload className="mx-auto w-6 h-6 text-muted-foreground mb-2" />
                  <input
                    type="file"
                    accept="image/*"
                    multiple
                    required
                    onChange={(e) => setEnrollFiles(e.target.files)}
                    className="text-xs text-muted-foreground file:mr-4 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-primary file:text-primary-foreground hover:file:bg-primary/90 cursor-pointer"
                  />
                  <p className="text-[11px] text-muted-foreground mt-2">
                    Upload 1–5 clear, well-lit portrait photos for FAISS embedding extraction
                  </p>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowEnrollModal(false)}
                  className="px-4 py-2 border border-border rounded-lg text-sm hover:bg-muted font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={enrolling}
                  className="px-5 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 transition flex items-center gap-2 disabled:opacity-50"
                >
                  {enrolling ? 'Extracting Vector...' : 'Save & Index Face'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
