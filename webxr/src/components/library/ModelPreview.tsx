import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js'
import type { SparkRenderer as SparkRendererType, SplatMesh as SplatMeshType } from '@sparkjsdev/spark'
import cycloneMark from '../../assets/cyclone-mark.webp'

export type ModelPreviewFormat = 'ply' | 'glb' | 'obj'

type ModelPreviewProps = {
  src?: string
  format?: ModelPreviewFormat
  name: string
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh
    mesh.geometry?.dispose()
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    materials.forEach((material) => material?.dispose())
  })
}

export default function ModelPreview({ src, format = 'ply', name }: ModelPreviewProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState(false)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    const host = hostRef.current
    setError(false)
    setLoaded(false)
    if (!host || !src) return

    let active = true
    let loadedObject: THREE.Object3D | undefined
    let splat: SplatMeshType | undefined
    let spark: SparkRendererType | undefined
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#17191d')
    const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 10000)
    camera.position.set(0, 0, 3)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
    host.replaceChildren(renderer.domElement)
    scene.add(new THREE.HemisphereLight(0xffffff, 0x55515a, 2))
    const light = new THREE.DirectionalLight(0xffffff, 2)
    light.position.set(2, 3, 4)
    scene.add(light)

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

    const fitObject = (object: THREE.Object3D) => {
      const bounds = new THREE.Box3().setFromObject(object)
      if (bounds.isEmpty()) return
      const center = bounds.getCenter(new THREE.Vector3())
      const size = bounds.getSize(new THREE.Vector3())
      object.position.sub(center)
      const maxSize = Math.max(size.x, size.y, size.z, 0.01)
      const distance = maxSize / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.35
      camera.position.set(0, 0, distance)
      camera.near = Math.max(maxSize / 1000, 0.001)
      camera.far = maxSize * 100
      camera.updateProjectionMatrix()
    }

    renderer.setAnimationLoop(() => renderer.render(scene, camera))
    const load = async () => {
      try {
        if (format === 'ply') {
          const { SparkRenderer, SplatMesh } = await import('@sparkjsdev/spark')
          if (!active) return
          spark = new SparkRenderer({ renderer })
          scene.add(spark)
          splat = new SplatMesh({ url: src })
          scene.add(splat)
          await splat.initialized
          if (!active) return
          camera.position.set(0, 0, 2.4)
        } else {
          const object = format === 'glb'
            ? (await new GLTFLoader().loadAsync(src)).scene
            : await new OBJLoader().loadAsync(src)
          if (!active) {
            disposeObject(object)
            return
          }
          loadedObject = object
          scene.add(object)
          fitObject(object)
        }
        if (active) setLoaded(true)
      } catch {
        if (active) setError(true)
      }
    }
    void load()

    return () => {
      active = false
      observer.disconnect()
      renderer.setAnimationLoop(null)
      if (loadedObject) disposeObject(loadedObject)
      splat?.dispose()
      spark?.dispose()
      renderer.dispose()
      host.replaceChildren()
    }
  }, [format, src])

  return (
    <div className="library-card-media" aria-label={`3D preview for ${name}`}>
      {!loaded ? (
        <div className="library-preview-placeholder" role={error ? 'status' : 'status'} aria-live="polite">
          <img src={cycloneMark} alt="" />
          <span>{error ? 'Preview unavailable' : 'Preparing preview…'}</span>
        </div>
      ) : null}
      <div className="library-preview-canvas" ref={hostRef} />
    </div>
  )
}
