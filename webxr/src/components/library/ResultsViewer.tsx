import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import cycloneMark from '../../assets/cyclone-mark.webp'
import { scansApi, type ScanArtifact } from '../../services/scans'

type RenderMode = 'textured' | 'points' | 'wireframe'
type AxisView = 'front' | 'top' | 'side'

function disposeModel(root: THREE.Object3D) {
  const geometries = new Set<THREE.BufferGeometry>()
  const materials = new Set<THREE.Material>()
  root.traverse((object) => {
    if ((object as THREE.Mesh).geometry) geometries.add((object as THREE.Mesh).geometry)
    const material = (object as THREE.Mesh).material
    if (Array.isArray(material)) material.forEach((item) => materials.add(item))
    else if (material) materials.add(material)
  })
  geometries.forEach((geometry) => geometry.dispose())
  const textures = new Set<THREE.Texture>()
  materials.forEach((material) => {
    for (const value of Object.values(material)) {
      if (value instanceof THREE.Texture) textures.add(value)
    }
    material.dispose()
  })
  textures.forEach((texture) => texture.dispose())
}

export default function ResultsViewer({ artifact }: { artifact: ScanArtifact | null }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const shellRef = useRef<HTMLDivElement>(null)
  const controlsRef = useRef<OrbitControls | null>(null)
  const gridRef = useRef<THREE.GridHelper | null>(null)
  const modelRootRef = useRef<THREE.Group | null>(null)
  const pointsGroupRef = useRef<THREE.Group | null>(null)
  const originalMaterialsRef = useRef(new WeakMap<THREE.Mesh, THREE.Material | THREE.Material[]>())
  const wireframeMaterialsRef = useRef(new WeakMap<THREE.Mesh, THREE.MeshBasicMaterial>())
  const [webglUnavailable, setWebglUnavailable] = useState(false)
  const [gridVisible, setGridVisible] = useState(true)
  const [renderMode, setRenderMode] = useState<RenderMode>('textured')
  const [autoRotate, setAutoRotate] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [loading, setLoading] = useState(false)

  const invalidate = useRef<() => void>(() => {})
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const hasSplat = useRef(false)
  const modeRef = useRef<RenderMode>('textured')

  function flipUpright() {
    const modelRoot = modelRootRef.current
    if (!modelRoot) return
    modelRoot.rotation.x = (modelRoot.rotation.x + Math.PI) % (Math.PI * 2)
    if (modeRef.current === 'points') applyRenderMode('points')
    invalidate.current()
  }

  function rotateQuarterTurn() {
    const modelRoot = modelRootRef.current
    if (!modelRoot) return
    modelRoot.rotation.y = (modelRoot.rotation.y + Math.PI / 2) % (Math.PI * 2)
    if (modeRef.current === 'points') applyRenderMode('points')
    invalidate.current()
  }

  function zoomBy(factor: number) {
    const controls = controlsRef.current
    if (!controls) return
    const offset = controls.object.position.clone().sub(controls.target).multiplyScalar(factor)
    controls.object.position.copy(controls.target).add(offset)
    controls.update()
  }

  function resetView() {
    const controls = controlsRef.current
    if (!controls) return
    controls.target.set(0, 0, 0)
    controls.object.position.set(7, 6, 8)
    controls.object.up.set(0, 1, 0)
    controls.update()
  }

  function setAxisView(view: AxisView) {
    const controls = controlsRef.current
    if (!controls) return
    const distance = controls.object.position.distanceTo(controls.target)
    const direction = view === 'front'
      ? new THREE.Vector3(0, 0, 1)
      : view === 'top'
        ? new THREE.Vector3(0, 1, 0)
        : new THREE.Vector3(1, 0, 0)
    controls.object.up.set(0, 1, 0)
    if (view === 'top') controls.object.up.set(0, 0, -1)
    controls.object.position.copy(controls.target).add(direction.multiplyScalar(distance))
    controls.update()
  }

  function applyRenderMode(mode: RenderMode) {
    modeRef.current = mode
    invalidate.current()
    setRenderMode(mode)
    const modelRoot = modelRootRef.current
    const pointsGroup = pointsGroupRef.current
    if (!modelRoot || !pointsGroup) return

    pointsGroup.traverse((object) => {
      if (object instanceof THREE.Points) {
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => material.dispose())
      }
    })
    pointsGroup.clear()

    const meshes: THREE.Mesh[] = []
    let containsPointCloud = false
    modelRoot.traverse((object) => {
      if ((object as THREE.Points).isPoints) containsPointCloud = true
      if ((object as THREE.Mesh).isMesh) meshes.push(object as THREE.Mesh)
    })
    meshes.forEach((mesh) => {
      if (!originalMaterialsRef.current.has(mesh)) {
        originalMaterialsRef.current.set(mesh, mesh.material)
      }
      mesh.material = originalMaterialsRef.current.get(mesh)!
      if (mode === 'wireframe') {
        let material = wireframeMaterialsRef.current.get(mesh)
        if (!material) {
          material = new THREE.MeshBasicMaterial({ color: 0xdfe6eb, wireframe: true })
          wireframeMaterialsRef.current.set(mesh, material)
        }
        mesh.material = material
      }
      if (mode === 'points') {
        mesh.updateWorldMatrix(true, false)
        const points = new THREE.Points(mesh.geometry, new THREE.PointsMaterial({ color: 0xdfe6eb, size: 0.025, sizeAttenuation: true }))
        points.matrixAutoUpdate = false
        points.matrix.copy(mesh.matrixWorld)
        pointsGroup.add(points)
      }
    })
    modelRoot.visible = mode !== 'points' || containsPointCloud || hasSplat.current
    pointsGroup.visible = mode === 'points'
  }

  function toggleAutoRotate() {
    const next = !autoRotate
    setAutoRotate(next)
    if (controlsRef.current) controlsRef.current.autoRotate = next
    invalidate.current()
  }

  async function toggleFullscreen() {
    const shell = shellRef.current
    if (!shell) return
    try {
      if (document.fullscreenElement === shell) await document.exitFullscreen()
      else await shell.requestFullscreen()
    } catch (error) {
      console.error('The 3D viewer could not enter fullscreen.', error)
    }
  }

  function toggleGrid() {
    const nextVisible = !gridVisible
    setGridVisible(nextVisible)
    if (gridRef.current) gridRef.current.visible = nextVisible
    invalidate.current()
  }

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    setWebglUnavailable(false)

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x25272a)
    const modelRoot = new THREE.Group()
    const pointsGroup = new THREE.Group()
    pointsGroup.visible = false
    scene.add(modelRoot, pointsGroup)
    modelRootRef.current = modelRoot
    pointsGroupRef.current = pointsGroup
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200)
    camera.position.set(7, 6, 8)

    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true })
    } catch (error) {
      console.error('The 3D viewport could not create a WebGL context.', error)
      setWebglUnavailable(true)
      return
    }
    rendererRef.current = renderer
    renderer.setClearColor(0x25272a, 1)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.replaceChildren(renderer.domElement)

    // Comprehensive studio lighting for photogrammetry scans
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x444455, 1.6)
    scene.add(hemiLight)

    const ambientLight = new THREE.AmbientLight(0xffffff, 1.4)
    scene.add(ambientLight)

    const keyLight = new THREE.DirectionalLight(0xffffff, 2.0)
    keyLight.position.set(10, 20, 15)
    scene.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0xffffff, 1.4)
    fillLight.position.set(-10, 10, -15)
    scene.add(fillLight)

    const bottomLight = new THREE.DirectionalLight(0xffffff, 0.8)
    bottomLight.position.set(0, -15, 0)
    scene.add(bottomLight)

    const grid = new THREE.GridHelper(24, 48, 0x87929c, 0x454d55)
    grid.material.transparent = true
    grid.material.opacity = 0.52
    grid.renderOrder = 1
    scene.add(grid)
    gridRef.current = grid

    const axes = new THREE.AxesHelper(4)
    axes.position.y = 0.008
    axes.renderOrder = 2
    scene.add(axes)

    camera.near = 0.01
    camera.far = 1000
    camera.updateProjectionMatrix()

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.enablePan = true
    controls.enableRotate = true
    controls.enableZoom = true
    controls.minDistance = 0.05
    controls.maxDistance = 500
    controls.minPolarAngle = 0
    controls.maxPolarAngle = Math.PI
    controls.screenSpacePanning = true
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
      RIGHT: THREE.MOUSE.PAN,
    }
    controls.target.set(0, 0, 0)
    controlsRef.current = controls

    const syncFullscreen = () => setIsFullscreen(document.fullscreenElement === shellRef.current)
    document.addEventListener('fullscreenchange', syncFullscreen)

    let frame = 0
    function render() {
      frame = 0
      controls.update()
      renderer.render(scene, camera)
      if (controls.autoRotate) requestFrame()
    }
    function requestFrame() {
      if (!frame) frame = requestAnimationFrame(render)
    }
    invalidate.current = requestFrame
    controls.addEventListener('change', requestFrame)
    const resize = () => {
      const width = Math.max(host.clientWidth, 1)
      const height = Math.max(host.clientHeight, 1)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
      requestFrame()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    resize()

    return () => {
      observer.disconnect()
      document.removeEventListener('fullscreenchange', syncFullscreen)
      controls.removeEventListener('change', requestFrame)
      cancelAnimationFrame(frame)
      invalidate.current = () => {}
      controls.dispose()
      controlsRef.current = null
      gridRef.current = null
      modelRootRef.current = null
      pointsGroupRef.current = null
      grid.geometry.dispose()
      const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material]
      gridMaterials.forEach((material) => material.dispose())
      axes.geometry.dispose()
      const axisMaterials = Array.isArray(axes.material) ? axes.material : [axes.material]
      axisMaterials.forEach((material) => material.dispose())
      rendererRef.current = null
      renderer.dispose()
      host.replaceChildren()
    }
  }, [])

  useEffect(() => {
    const modelRoot = modelRootRef.current
    const pointsGroup = pointsGroupRef.current
    if (!modelRoot || !pointsGroup) return
    modelRoot.clear()
    pointsGroup.clear()
    invalidate.current()
    if (!artifact) {
      setLoading(false)
      setLoadError(false)
      return
    }
    const controller = new AbortController()
    let disposeSplat: (() => void) | undefined
    let splatBounds: THREE.Box3 | undefined
    let cancelled = false
    setLoadError(false)
    setLoading(true)

    async function loadArtifact(artifact: ScanArtifact, modelRoot: THREE.Group) {
      try {
        let loaded: THREE.Object3D
        const blob = await scansApi.artifact(artifact.id, controller.signal)
        if (cancelled) return
        const extension = artifact.filename.split('.').pop()?.toLowerCase()
        if (extension === 'glb' || extension === 'gltf') {
          const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js')
          if (cancelled) return
          const data = await blob.arrayBuffer()
          const parsed = await new GLTFLoader().parseAsync(data, '')
          loaded = parsed.scene
        } else if (extension === 'obj') {
          const { OBJLoader } = await import('three/addons/loaders/OBJLoader.js')
          if (cancelled) return
          loaded = new OBJLoader().parse(await blob.text())
        } else if (extension === 'ply' && !/^scene(?:\.compressed)?\.ply$/i.test(artifact.filename)) {
          const { PLYLoader } = await import('three/addons/loaders/PLYLoader.js')
          if (cancelled) return
          const geometry = new PLYLoader().parse(await blob.arrayBuffer())
          geometry.computeBoundingSphere()
          if (geometry.hasAttribute('color')) {
            loaded = new THREE.Points(geometry, new THREE.PointsMaterial({ size: 0.01, vertexColors: true, sizeAttenuation: true }))
          } else {
            loaded = new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xdfe6eb, size: 0.01, sizeAttenuation: true }))
          }
        } else if (extension === 'usdz') {
          const { USDZLoader } = await import('three/addons/loaders/USDZLoader.js')
          if (cancelled) return
          loaded = new USDZLoader().parse(await blob.arrayBuffer())
        } else if (extension === 'spz' || extension === 'ply') {
          const { SparkRenderer, SplatMesh } = await import('@sparkjsdev/spark')
          const bytes = await blob.arrayBuffer()
          if (cancelled) return
          const splat = new SplatMesh({ fileBytes: bytes, fileName: artifact.filename })
          try {
            await splat.initialized
          } catch (error) {
            splat.dispose()
            throw error
          }
          if (cancelled) { splat.dispose(); return }
          const renderer = rendererRef.current
          const scene = modelRoot.parent
          if (!renderer || !scene) { splat.dispose(); return }
          const spark = new SparkRenderer({ renderer, onDirty: () => invalidate.current() })
          scene.add(spark)
          disposeSplat = () => {
            splat.removeFromParent()
            spark.removeFromParent()
            splat.dispose()
            spark.dispose()
          }
          hasSplat.current = true
          splatBounds = splat.getBoundingBox()
          loaded = splat
        } else {
          throw new Error(`Unsupported result format: ${extension ?? 'unknown'}`)
        }
        if (cancelled) {
          disposeModel(loaded)
          return
        }

        // Ensure all mesh faces are double-sided so inverted normals or backfaces are fully visible
        loaded.traverse((child) => {
          if ((child as THREE.Mesh).isMesh) {
            const mesh = child as THREE.Mesh
            const mat = mesh.material
            const materials = Array.isArray(mat) ? mat : [mat]
            materials.forEach((m) => {
              if (m) {
                m.side = THREE.DoubleSide
                m.shadowSide = THREE.DoubleSide
                m.needsUpdate = true
              }
            })
          }
        })

        modelRoot.add(loaded)
        const bounds = splatBounds ?? new THREE.Box3().setFromObject(loaded)
        if (!bounds.isEmpty()) {
          const center = bounds.getCenter(new THREE.Vector3())
          const size = bounds.getSize(new THREE.Vector3())
          loaded.position.sub(center)
          const maxDim = Math.max(size.x, size.y, size.z, 1)
          const distance = maxDim * 1.6
          const controls = controlsRef.current
          if (controls) {
            controls.target.set(0, 0, 0)
            controls.object.position.set(distance * 0.8, distance * 0.6, distance)
            controls.minDistance = Math.max(maxDim * 0.05, 0.01)
            controls.maxDistance = Math.max(maxDim * 10, 100)
            controls.update()
          }
        }
        applyRenderMode(modeRef.current)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void loadArtifact(artifact, modelRoot).catch((error: unknown) => {
      if (!cancelled) {
        console.error('The scan result could not be loaded into the viewer.', error)
        setLoadError(true)
      }
    })
    return () => {
      cancelled = true
      controller.abort()
      hasSplat.current = false
      disposeSplat?.()
      pointsGroup.traverse((object) => {
        if (object instanceof THREE.Points) object.material.dispose()
      })
      modelRoot.traverse((object) => {
        const wireframe = wireframeMaterialsRef.current.get(object as THREE.Mesh)
        const original = originalMaterialsRef.current.get(object as THREE.Mesh)
        if (original) (object as THREE.Mesh).material = original
        wireframe?.dispose()
      })
      disposeModel(modelRoot)
      modelRoot.clear()
      pointsGroup.clear()
    }
  }, [artifact?.id])

  return (
    <div className="results-viewer-shell" ref={shellRef} aria-label="Interactive 3D viewport. Middle-drag to orbit, scroll to zoom, and right-drag to pan.">
      <div className="results-viewer-canvas" ref={hostRef} />
      <div className="results-viewer-modes" role="group" aria-label="Object display mode">
        {(['textured', 'points', 'wireframe'] as const).map((mode) => (
          <button key={mode} type="button" className={renderMode === mode ? 'is-active' : ''} aria-pressed={renderMode === mode} onClick={() => applyRenderMode(mode)} disabled={webglUnavailable}>
            {mode === 'textured' ? 'Textured' : mode === 'points' ? 'Points' : 'Wireframe'}
          </button>
        ))}
      </div>
      <div className="results-viewer-axis-views" role="group" aria-label="Axis views">
        <button type="button" onClick={() => setAxisView('front')} title="Front view along Z">Front <span>Z</span></button>
        <button type="button" onClick={() => setAxisView('top')} title="Top view along Y">Top <span>Y</span></button>
        <button type="button" onClick={() => setAxisView('side')} title="Side view along X">Side <span>X</span></button>
      </div>
      <div className="results-viewer-tools" role="toolbar" aria-label="Viewer controls">
        <button type="button" aria-label="Reset view" title="Reset view" onClick={resetView} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m3 9 7-6 7 6M5.5 8v8.5h9V8M8 16.5v-5h4v5" /></svg>
        </button>
        <button type="button" aria-label="Flip upright" title="Flip upright (invert vertical)" onClick={flipUpright} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5v15M14 6.5l-4-4-4 4M6 13.5l4 4 4-4" /></svg>
        </button>
        <button type="button" aria-label="Rotate 90 degrees" title="Rotate 90°" onClick={rotateQuarterTurn} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16 10A6 6 0 1 1 14.2 5.8L16 4M16 4v4.5M16 4h-4.5" /></svg>
        </button>
        <button type="button" aria-label="Zoom in" title="Zoom in" onClick={() => zoomBy(0.8)} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="M12.5 12.5 17 17M8.5 6v5M6 8.5h5" /></svg>
        </button>
        <button type="button" aria-label="Zoom out" title="Zoom out" onClick={() => zoomBy(1.25)} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" /><path d="M12.5 12.5 17 17M6 8.5h5" /></svg>
        </button>
        <button type="button" aria-label={gridVisible ? 'Hide grid' : 'Show grid'} title={gridVisible ? 'Hide grid' : 'Show grid'} aria-pressed={gridVisible} onClick={toggleGrid} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m10 2 7 4v8l-7 4-7-4V6l7-4ZM3 6l7 4 7-4M10 10v8M6.5 4l7 4M13.5 4l-7 4" /></svg>
        </button>
        <button type="button" aria-label={autoRotate ? 'Stop auto rotate' : 'Start auto rotate'} title={autoRotate ? 'Stop auto rotate' : 'Auto rotate'} aria-pressed={autoRotate} onClick={toggleAutoRotate} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M16.5 8A6.5 6.5 0 0 0 5.2 4.2L3.5 6M3.5 6V2.8M3.5 6h3.2M3.5 12A6.5 6.5 0 0 0 14.8 15.8l1.7-1.8M16.5 14v3.2M16.5 14h-3.2" /></svg>
        </button>
        <button type="button" aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'} title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'} aria-pressed={isFullscreen} onClick={toggleFullscreen} disabled={webglUnavailable}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M7 3H3v4M13 3h4v4M17 13v4h-4M3 13v4h4" /></svg>
        </button>
      </div>
      {loading && (
        <div className="results-viewer-loading" role="status" aria-label="Loading 3D model">
          <img src={cycloneMark} alt="" />
        </div>
      )}
      {(webglUnavailable || loadError) && (
        <div className="results-webgl-fallback" role="status">
          <img src={cycloneMark} alt="" />
        </div>
      )}
    </div>
  )
}
