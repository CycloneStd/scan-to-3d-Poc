const imageCards = [
  { position: 'top-left-center', photoId: 3778080 },
  { position: 'top-right-center', photoId: 36297579 },
  { position: 'top-right', photoId: 29093113 },
  { position: 'left-upper', photoId: 8516708 },
  { position: 'left-lower', photoId: 8307237 },
  { position: 'right-upper', photoId: 6615808 },
  { position: 'right-lower', photoId: 18041821 },
  { position: 'bottom-left', photoId: 18497614 },
  { position: 'bottom-left-center', photoId: 4029473 },
  { position: 'bottom-right-center', photoId: 5807742 },
  { position: 'bottom-right', photoId: 14179353 },
]

export default function LoginImageCards() {
  return (
    <div className="login-image-field" aria-hidden="true">
      {imageCards.map(({ position, photoId }) => (
        <figure
          className={`login-image-card global-card rounded-surface-md bg-surface-low ${position}`}
          key={position}
        >
          <img
            src={`https://images.pexels.com/photos/${photoId}/pexels-photo-${photoId}.jpeg?auto=compress&cs=tinysrgb&w=480&q=75`}
            alt=""
            loading="eager"
            draggable="false"
          />
        </figure>
      ))}
    </div>
  )
}
