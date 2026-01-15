'use client'

import { useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Download, ZoomIn, ZoomOut, X } from 'lucide-react'
import type { PropertyAnalysis } from '@/types'
import { cn } from '@/lib/utils'

interface AnalysisImageViewerProps {
  analysis: PropertyAnalysis
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ImageType = 'wide_satellite' | 'segmentation' | 'property_boundary' | 'condition_analysis'

const IMAGE_LABELS: Record<ImageType, string> = {
  wide_satellite: 'Original Satellite',
  segmentation: 'CV Segmentation',
  property_boundary: 'Property Asphalt',
  condition_analysis: 'Condition Analysis',
}

const IMAGE_DESCRIPTIONS: Record<ImageType, string> = {
  wide_satellite: 'Original satellite imagery of the property area',
  segmentation: 'All detected buildings (green) and paved surfaces (blue)',
  property_boundary: 'Only asphalt areas belonging to this property, with excluded areas dimmed',
  condition_analysis: 'Damage detections including cracks (yellow) and potholes (red)',
}

export function AnalysisImageViewer({ 
  analysis, 
  open, 
  onOpenChange 
}: AnalysisImageViewerProps) {
  const [selectedImage, setSelectedImage] = useState<ImageType>('condition_analysis')
  const [zoom, setZoom] = useState(1)

  // Convert base64 to data URL if needed
  const toDataUrl = (base64: string | undefined): string | undefined => {
    if (!base64) return undefined
    if (base64.startsWith('http') || base64.startsWith('data:')) return base64
    return `data:image/jpeg;base64,${base64}`
  }

  const images: { key: ImageType; src: string | undefined }[] = [
    { key: 'wide_satellite' as ImageType, src: toDataUrl(analysis.images.wide_satellite) },
    { key: 'segmentation' as ImageType, src: toDataUrl(analysis.images.segmentation) },
    { key: 'property_boundary' as ImageType, src: toDataUrl(analysis.images.property_boundary) },
    { key: 'condition_analysis' as ImageType, src: toDataUrl(analysis.images.condition_analysis) },
  ].filter(img => img.src)

  const currentImage = images.find(img => img.key === selectedImage)

  const handleDownload = () => {
    if (currentImage?.src) {
      const link = document.createElement('a')
      link.href = currentImage.src
      link.download = `${analysis.id}_${selectedImage}.jpg`
      link.click()
    }
  }

  const handleZoomIn = () => setZoom(z => Math.min(z + 0.25, 3))
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.25, 0.5))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-full h-[90vh] flex flex-col p-0">
        <DialogHeader className="p-4 border-b">
          <div className="flex items-center justify-between">
            <DialogTitle>{IMAGE_LABELS[selectedImage]}</DialogTitle>
            <div className="flex items-center gap-2">
              <Button size="icon" variant="ghost" onClick={handleZoomOut}>
                <ZoomOut className="h-4 w-4" />
              </Button>
              <span className="text-sm text-gray-500 w-12 text-center">
                {Math.round(zoom * 100)}%
              </span>
              <Button size="icon" variant="ghost" onClick={handleZoomIn}>
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" onClick={handleDownload}>
                <Download className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" onClick={() => onOpenChange(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* Main Image */}
        <div className="flex-1 overflow-auto bg-gray-900 flex items-center justify-center">
          {currentImage?.src && (
            <div 
              className="relative transition-transform duration-200"
              style={{ transform: `scale(${zoom})` }}
            >
              <img
                src={currentImage.src}
                alt={IMAGE_LABELS[selectedImage]}
                className="max-w-none max-h-full"
              />
            </div>
          )}
        </div>

        {/* Description */}
        <div className="p-3 bg-gray-100 border-t text-sm text-gray-600">
          {IMAGE_DESCRIPTIONS[selectedImage]}
        </div>

        {/* Thumbnail Strip */}
        <div className="p-3 border-t bg-white">
          <div className="flex gap-2 overflow-x-auto">
            {images.map((img) => (
              <button
                key={img.key}
                onClick={() => {
                  setSelectedImage(img.key)
                  setZoom(1)
                }}
                className={cn(
                  "flex-shrink-0 rounded-lg overflow-hidden border-2 transition-all",
                  selectedImage === img.key 
                    ? "border-blue-500 ring-2 ring-blue-200" 
                    : "border-transparent hover:border-gray-300"
                )}
              >
                <div className="relative w-24 h-16">
                  {img.src && (
                    <img
                      src={img.src}
                      alt={IMAGE_LABELS[img.key]}
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  )}
                </div>
                <div className="text-xs text-center py-1 bg-gray-50 truncate px-1">
                  {IMAGE_LABELS[img.key]}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        {selectedImage !== 'wide_satellite' && (
          <div className="p-3 border-t bg-gray-50">
            <ImageLegend imageType={selectedImage} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ImageLegend({ imageType }: { imageType: ImageType }) {
  if (imageType === 'wide_satellite') return null

  const legends: Record<ImageType, { color: string; label: string }[]> = {
    wide_satellite: [],
    segmentation: [
      { color: 'bg-green-500', label: 'Buildings' },
      { color: 'bg-blue-500', label: 'Paved Surfaces' },
      { color: 'bg-yellow-500', label: 'Business Building' },
    ],
    property_boundary: [
      { color: 'bg-yellow-500', label: 'Business Building' },
      { color: 'bg-blue-500', label: 'Property Asphalt' },
      { color: 'bg-gray-400', label: 'Excluded (public/neighbor)' },
    ],
    condition_analysis: [
      { color: 'bg-blue-400', label: 'Property Asphalt' },
      { color: 'bg-yellow-500', label: 'Cracks' },
      { color: 'bg-red-500', label: 'Potholes' },
      { color: 'bg-orange-500', label: 'Alligator Cracks' },
    ],
  }

  const items = legends[imageType]

  return (
    <div className="flex flex-wrap gap-4">
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
          <div className={cn("w-4 h-4 rounded", item.color)} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  )
}

