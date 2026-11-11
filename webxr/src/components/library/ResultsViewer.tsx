import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import cycloneMark from '../../assets/cyclone-mark.png'

type RenderMode = 'textured' | 'points' | 'wireframe'
type AxisView = 'front' | 'top' | 'side'

export default function ResultsViewer() {
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
    modelRoot.traverse((object) => {
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
    modelRoot.visible = mode !== 'points'
    pointsGroup.visible = mode === 'points'
  }

  function toggleAutoRotate() {
    const next = !autoRotate
    setAutoRotate(next)
    if (controlsRef.current) controlsRef.current.autoRotate = next
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
    renderer.setClearColor(0x25272a, 1)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    host.replaceChildren(renderer.domElement)

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

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.enablePan = true
    controls.enableRotate = true
    controls.enableZoom = true
    controls.minDistance = 1
    controls.maxDistance = 40
    controls.minPolarAngle = 0
    controls.maxPolarAngle = Math.PI
    controls.screenSpacePanning = true
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.ROTATE,
      RIGHT: THREE.MOUSE.PAN,
    }
    controls.target.set(0, 0, 0)
    controlsRef.current = controls

    const syncFullscreen = () => setIsFullscreen(document.fullscreenElement === shellRef.current)
    document.addEventListener('fullscreenchange', syncFullscreen)

    const resize = () => {
      const width = Math.max(host.clientWidth, 1)
      const height = Math.max(host.clientHeight, 1)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
      renderer.setSize(width, height, false)
    }
    const observer = new ResizeObserver(resize)
    observer.observe(host)
    resize()

    renderer.setAnimationLoop(() => {
      controls.update()
      renderer.render(scene, camera)
    })

    return () => {
      observer.disconnect()
      document.removeEventListener('fullscreenchange', syncFullscreen)
      renderer.setAnimationLoop(null)
      controls.dispose()
      controlsRef.current = null
      gridRef.current = null
      modelRootRef.current = null
      pointsGroupRef.current = null
      pointsGroup.traverse((object) => {
        if (object instanceof THREE.Points) object.material.dispose()
      })
      modelRoot.traverse((object) => {
        const material = wireframeMaterialsRef.current.get(object as THREE.Mesh)
        material?.dispose()
      })
      grid.geometry.dispose()
      const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material]
      gridMaterials.forEach((material) => material.dispose())
      axes.geometry.dispose()
      const axisMaterials = Array.isArray(axes.material) ? axes.material : [axes.material]
      axisMaterials.forEach((material) => material.dispose())
      renderer.dispose()
      host.replaceChildren()
    }
  }, [])

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
      {webglUnavailable && (
        <div className="results-webgl-fallback" role="status">
          <img src={cycloneMark} alt="" />
        </div>
      )}
    </div>
  )
}
