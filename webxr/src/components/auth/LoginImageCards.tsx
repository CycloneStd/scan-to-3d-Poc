import photo3778080 from '../../assets/login-cards/3778080.webp'
import photo36297579 from '../../assets/login-cards/36297579.webp'
import photo29093113 from '../../assets/login-cards/29093113.webp'
import photo8516708 from '../../assets/login-cards/8516708.webp'
import photo8307237 from '../../assets/login-cards/8307237.webp'
import photo6615808 from '../../assets/login-cards/6615808.webp'
import photo18041821 from '../../assets/login-cards/18041821.webp'
import photo18497614 from '../../assets/login-cards/18497614.webp'
import photo4029473 from '../../assets/login-cards/4029473.webp'
import photo5807742 from '../../assets/login-cards/5807742.webp'
import photo14179353 from '../../assets/login-cards/14179353.webp'

const imageCards = [
  { position: 'top-left-center', src: photo3778080 },
  { position: 'top-right-center', src: photo36297579 },
  { position: 'top-right', src: photo29093113 },
  { position: 'left-upper', src: photo8516708 },
  { position: 'left-lower', src: photo8307237 },
  { position: 'right-upper', src: photo6615808 },
  { position: 'right-lower', src: photo18041821 },
  { position: 'bottom-left', src: photo18497614 },
  { position: 'bottom-left-center', src: photo4029473 },
  { position: 'bottom-right-center', src: photo5807742 },
  { position: 'bottom-right', src: photo14179353 },
]

let imagesReady: Promise<void> | undefined

export function preloadLoginImages() {
  if (window.matchMedia('(max-width: 520px)').matches) return Promise.resolve()
  if (imagesReady) return imagesReady

  const visibleCards = window.matchMedia('(max-width: 760px)').matches
    ? imageCards.filter(({ position }) => !['top-left-center', 'top-right-center', 'bottom-left-center', 'bottom-right-center'].includes(position))
    : imageCards

  imagesReady = Promise.all(visibleCards.map(({ src }) => {
    const image = new Image()
    image.src = src
    return image.decode().catch(() => undefined)
  })).then(() => undefined)
  return imagesReady
}

export default function LoginImageCards() {
  return (
    <div className="login-image-field" aria-hidden="true">
      {imageCards.map(({ position, src }) => (
        <figure
          className={`login-image-card global-card rounded-surface-md bg-surface-low ${position}`}
          key={position}
        >
          <img
            src={src}
            alt=""
            loading="lazy"
            fetchPriority="low"
            draggable="false"
          />
        </figure>
      ))}
    </div>
  )
}
