'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, UserSettings, UpdateOpenRouterKeyRequest } from '@/lib/api/settings'
import { scoringPromptsApi, ScoringPrompt, CreateScoringPromptRequest } from '@/lib/api/scoring-prompts'
import { cn } from '@/lib/utils'
import { 
  Key,
  Eye,
  EyeOff,
  Check,
  X,
  AlertCircle,
  ExternalLink,
  Loader2,
  Building2,
  Phone,
  Mail,
  Lock,
  Sparkles,
  FileText,
  Plus,
  Edit2,
  Trash2,
  Star,
} from 'lucide-react'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  
  const { data: settings, isLoading, error } = useQuery<UserSettings>({
    queryKey: ['settings'],
    queryFn: settingsApi.getSettings,
  })

  const [showKey, setShowKey] = useState(false)
  const [newApiKey, setNewApiKey] = useState('')
  const [isEditingKey, setIsEditingKey] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Mutations
  const updateKeyMutation = useMutation({
    mutationFn: (data: UpdateOpenRouterKeyRequest) => settingsApi.updateOpenRouterKey(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setIsEditingKey(false)
      setNewApiKey('')
      showSuccess('API key updated successfully')
    },
    onError: (err: any) => {
      showError(err.response?.data?.detail || 'Failed to update API key')
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: settingsApi.deleteOpenRouterKey,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      showSuccess('API key removed')
    },
    onError: () => {
      showError('Failed to remove API key')
    },
  })

  const showSuccess = (msg: string) => {
    setSaveSuccess(msg)
    setSaveError(null)
    setTimeout(() => setSaveSuccess(null), 3000)
  }

  const showError = (msg: string) => {
    setSaveError(msg)
    setSaveSuccess(null)
    setTimeout(() => setSaveError(null), 5000)
  }

  const handleToggleEnabled = () => {
    if (!settings) return
    updateKeyMutation.mutate({
      enabled: !settings.use_own_openrouter_key,
    })
  }

  const handleSaveKey = () => {
    if (!newApiKey.trim()) {
      showError('Please enter an API key')
      return
    }
    updateKeyMutation.mutate({
      api_key: newApiKey.trim(),
      enabled: true,
    })
  }

  const handleRemoveKey = () => {
    if (confirm('Remove your OpenRouter API key?')) {
      deleteKeyMutation.mutate()
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-full bg-stone-100 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-6 w-6 animate-spin text-stone-400" />
          <span className="text-sm text-stone-500">Loading settings...</span>
        </div>
      </div>
    )
  }

  if (error || !settings) {
    return (
      <div className="min-h-full bg-stone-100 flex items-center justify-center">
        <div className="bg-white rounded-xl border border-stone-200 p-6 text-center">
          <AlertCircle className="h-8 w-8 text-red-500 mx-auto mb-2" />
          <p className="text-sm text-stone-600">Failed to load settings</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-full bg-stone-100 p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-semibold text-stone-800">Settings</h1>
          <p className="text-sm text-stone-500">Manage your account and API keys</p>
        </div>

        {/* Success/Error Messages */}
        {saveSuccess && (
          <div className="flex items-center gap-2 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700">
            <Check className="h-4 w-4" />
            {saveSuccess}
          </div>
        )}
        {saveError && (
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertCircle className="h-4 w-4" />
            {saveError}
          </div>
        )}

        {/* Profile Section */}
        <section className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-stone-100 flex items-center gap-2">
            <Building2 className="h-4 w-4 text-stone-500" />
            <h2 className="text-sm font-semibold text-stone-700">Profile</h2>
          </div>
          <div className="p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Mail className="h-4 w-4 text-stone-400" />
                <div>
                  <p className="text-xs text-stone-500">Email</p>
                  <p className="text-sm font-medium text-stone-700">{settings.email}</p>
                </div>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Building2 className="h-4 w-4 text-stone-400" />
                <div>
                  <p className="text-xs text-stone-500">Company</p>
                  <p className="text-sm font-medium text-stone-700">{settings.company_name}</p>
                </div>
              </div>
            </div>
            {settings.phone && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Phone className="h-4 w-4 text-stone-400" />
                  <div>
                    <p className="text-xs text-stone-500">Phone</p>
                    <p className="text-sm font-medium text-stone-700">{settings.phone}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* OpenRouter API Key Section */}
        <section className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-stone-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Key className="h-4 w-4 text-violet-500" />
              <h2 className="text-sm font-semibold text-stone-700">OpenRouter API Key</h2>
            </div>
            <a 
              href="https://openrouter.ai/keys" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-violet-600 hover:text-violet-700"
            >
              Get a key
              <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          
          <div className="p-5 space-y-4">
            {/* Explanation */}
            <div className="flex items-start gap-3 p-3 bg-stone-50 rounded-lg">
              <Sparkles className="h-4 w-4 text-violet-500 mt-0.5" />
              <div className="text-xs text-stone-600">
                <p className="font-medium text-stone-700 mb-1">Use your own OpenRouter account</p>
                <p>
                  Add your own API key to use your OpenRouter credits for VLM analysis. 
                  This gives you control over costs and usage limits.
                </p>
              </div>
            </div>

            {/* Current Key Status */}
            {settings.has_openrouter_key && !isEditingKey ? (
              <div className="space-y-3">
                {/* Key Display */}
                <div className="flex items-center justify-between p-3 bg-stone-50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded bg-violet-100 flex items-center justify-center">
                      <Key className="h-4 w-4 text-violet-600" />
                    </div>
                    <div>
                      <p className="text-xs text-stone-500">Your API Key</p>
                      <p className="text-sm font-mono text-stone-700">
                        {showKey ? settings.openrouter_key_preview : '••••••••••••'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowKey(!showKey)}
                      className="p-1.5 rounded hover:bg-stone-200 transition-colors"
                    >
                      {showKey ? (
                        <EyeOff className="h-4 w-4 text-stone-500" />
                      ) : (
                        <Eye className="h-4 w-4 text-stone-500" />
                      )}
                    </button>
                    <button
                      onClick={() => setIsEditingKey(true)}
                      className="text-xs text-violet-600 hover:text-violet-700 font-medium"
                    >
                      Change
                    </button>
                  </div>
                </div>

                {/* Enable Toggle */}
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-stone-700">Use my own key</p>
                    <p className="text-xs text-stone-500">
                      {settings.use_own_openrouter_key 
                        ? 'Your API key is being used for VLM analysis'
                        : 'System key is being used (if available)'}
                    </p>
                  </div>
                  <button
                    onClick={handleToggleEnabled}
                    disabled={updateKeyMutation.isPending}
                    className={cn(
                      'relative w-11 h-6 rounded-full transition-colors',
                      settings.use_own_openrouter_key ? 'bg-violet-500' : 'bg-stone-300'
                    )}
                  >
                    <div className={cn(
                      'absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform',
                      settings.use_own_openrouter_key ? 'left-6' : 'left-1'
                    )} />
                  </button>
                </div>

                {/* Remove Button */}
                <button
                  onClick={handleRemoveKey}
                  disabled={deleteKeyMutation.isPending}
                  className="text-xs text-red-600 hover:text-red-700 font-medium"
                >
                  Remove API key
                </button>
              </div>
            ) : (
              /* Add/Edit Key Form */
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-stone-600 mb-1.5">
                    {settings.has_openrouter_key ? 'New API Key' : 'API Key'}
                  </label>
                  <input
                    type="password"
                    value={newApiKey}
                    onChange={(e) => setNewApiKey(e.target.value)}
                    placeholder="sk-or-v1-..."
                    className="w-full px-3 py-2 text-sm border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent font-mono"
                  />
                  <p className="text-[11px] text-stone-400 mt-1">
                    Your key is stored securely and never shared
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSaveKey}
                    disabled={updateKeyMutation.isPending || !newApiKey.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {updateKeyMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Check className="h-3.5 w-3.5" />
                    )}
                    Save Key
                  </button>
                  {isEditingKey && (
                    <button
                      onClick={() => { setIsEditingKey(false); setNewApiKey('') }}
                      className="flex items-center gap-1.5 px-4 py-2 bg-stone-100 text-stone-600 text-sm font-medium rounded-lg hover:bg-stone-200 transition-colors"
                    >
                      <X className="h-3.5 w-3.5" />
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Scoring Prompts Section */}
        <ScoringPromptsSection />

        {/* Security Section */}
        <section className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-stone-100 flex items-center gap-2">
            <Lock className="h-4 w-4 text-stone-500" />
            <h2 className="text-sm font-semibold text-stone-700">Security</h2>
          </div>
          <div className="p-5">
            <button
              onClick={() => alert('Password change coming soon')}
              className="text-sm text-violet-600 hover:text-violet-700 font-medium"
            >
              Change password →
            </button>
          </div>
        </section>

        {/* Footer */}
        <p className="text-center text-xs text-stone-400">
          Need help? Contact support@worksight.io
        </p>
      </div>
    </div>
  )
}

function ScoringPromptsSection() {
  const queryClient = useQueryClient()
  const [isCreating, setIsCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [newTitle, setNewTitle] = useState('')
  const [newPrompt, setNewPrompt] = useState('')
  const [isDefault, setIsDefault] = useState(false)

  const { data: prompts, isLoading } = useQuery({
    queryKey: ['scoring-prompts'],
    queryFn: scoringPromptsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: (data: CreateScoringPromptRequest) => scoringPromptsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scoring-prompts'] })
      setIsCreating(false)
      setNewTitle('')
      setNewPrompt('')
      setIsDefault(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => scoringPromptsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scoring-prompts'] })
      setEditingId(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => scoringPromptsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scoring-prompts'] })
    },
  })

  const handleCreate = () => {
    if (!newTitle.trim() || !newPrompt.trim()) return
    createMutation.mutate({
      title: newTitle.trim(),
      prompt: newPrompt.trim(),
      is_default: isDefault,
    })
  }

  const handleEdit = (prompt: ScoringPrompt) => {
    setEditingId(prompt.id)
    setNewTitle(prompt.title)
    setNewPrompt(prompt.prompt)
    setIsDefault(prompt.is_default)
  }

  const handleUpdate = (id: string) => {
    if (!newTitle.trim() || !newPrompt.trim()) return
    updateMutation.mutate({
      id,
      data: {
        title: newTitle.trim(),
        prompt: newPrompt.trim(),
        is_default: isDefault,
      },
    })
  }

  const handleDelete = (id: string) => {
    if (confirm('Delete this scoring prompt?')) {
      deleteMutation.mutate(id)
    }
  }

  return (
    <section className="bg-white rounded-xl border border-stone-200 overflow-hidden">
      <div className="px-5 py-4 border-b border-stone-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-amber-500" />
          <h2 className="text-sm font-semibold text-stone-700">Lead Scoring Prompts</h2>
        </div>
        {!isCreating && !editingId && (
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-violet-600 hover:text-violet-700 hover:bg-violet-50 rounded-lg transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New Prompt
          </button>
        )}
      </div>

      <div className="p-5 space-y-4">
        {/* Create/Edit Form */}
        {(isCreating || editingId) && (
          <div className="p-4 bg-stone-50 rounded-lg border border-stone-200 space-y-3">
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1.5">
                Title
              </label>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g., High-Value Commercial Leads"
                className="w-full px-3 py-2 text-sm border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1.5">
                Scoring Criteria
              </label>
              <textarea
                value={newPrompt}
                onChange={(e) => setNewPrompt(e.target.value)}
                placeholder="HIGH (80-100): Large parking areas with visible damage..."
                rows={6}
                className="w-full px-3 py-2 text-sm border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent resize-none"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is-default"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="w-4 h-4 rounded border-stone-300 text-violet-600 focus:ring-violet-500"
              />
              <label htmlFor="is-default" className="text-xs text-stone-600">
                Set as default (used automatically in discovery)
              </label>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => editingId ? handleUpdate(editingId) : handleCreate()}
                disabled={!newTitle.trim() || !newPrompt.trim() || createMutation.isPending || updateMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {(createMutation.isPending || updateMutation.isPending) ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                {editingId ? 'Update' : 'Create'}
              </button>
              <button
                onClick={() => {
                  setIsCreating(false)
                  setEditingId(null)
                  setNewTitle('')
                  setNewPrompt('')
                  setIsDefault(false)
                }}
                className="flex items-center gap-1.5 px-4 py-2 bg-stone-100 text-stone-600 text-sm font-medium rounded-lg hover:bg-stone-200 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Prompts List */}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-stone-400" />
          </div>
        ) : prompts && prompts.length > 0 ? (
          <div className="space-y-2">
            {prompts.map((prompt) => (
              <div
                key={prompt.id}
                className={cn(
                  'p-3 rounded-lg border transition-all',
                  prompt.is_default
                    ? 'bg-amber-50 border-amber-200'
                    : 'bg-stone-50 border-stone-200'
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-stone-700 truncate">
                        {prompt.title}
                      </h3>
                      {prompt.is_default && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-[10px] font-medium">
                          <Star className="h-2.5 w-2.5 fill-current" />
                          Default
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-stone-500 line-clamp-2">{prompt.prompt}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleEdit(prompt)}
                      className="p-1.5 rounded hover:bg-stone-200 transition-colors"
                      title="Edit"
                    >
                      <Edit2 className="h-3.5 w-3.5 text-stone-500" />
                    </button>
                    <button
                      onClick={() => handleDelete(prompt.id)}
                      className="p-1.5 rounded hover:bg-red-50 transition-colors"
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5 text-red-500" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : !isCreating ? (
          <div className="text-center py-8">
            <FileText className="h-8 w-8 text-stone-300 mx-auto mb-2" />
            <p className="text-sm text-stone-500">No scoring prompts yet</p>
            <p className="text-xs text-stone-400 mt-1">Create one to use in discovery</p>
          </div>
        ) : null}
      </div>
    </section>
  )
}

